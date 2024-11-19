# It is currently shipped inside msal library.
# Pros: It is always available wherever msal is installed.
# Cons: Its 3rd-party dependencies (if any) may become msal's dependency.
"""MSAL Python Tester

Usage 1: Run it on the fly.
    python -m msal
    Note: We choose to not define a console script to avoid name conflict.

Usage 2: Build an all-in-one executable file for bug bash.
    shiv -e msal.__main__._main -o msaltest-on-os-name.pyz .
"""
import base64, getpass, json, logging, sys, os, atexit, msal
from typing import Any, Callable, Dict, List, Optional, Union

_token_cache_filename = "msal_cache.bin"
global_cache = msal.SerializableTokenCache()
atexit.register(lambda:
    open(_token_cache_filename, "w").write(global_cache.serialize())
    # Hint: The following optional line persists only when state changed
    if global_cache.has_state_changed else None
    )

_AZURE_CLI = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
_VISUAL_STUDIO = "04f0c124-f2bc-4f59-8241-bf6df9866bbd"
placeholder_auth_scheme = msal.PopAuthScheme(
    http_method=msal.PopAuthScheme.HTTP_GET,
    url="https://example.com/endpoint",
    nonce="placeholder",
    )

def print_json(blob: Dict[str, Any]) -> None:
    print(json.dumps(blob, indent=2, sort_keys=True))

def _input_boolean(message: str) -> bool:
    return input(
        "{} (N/n/F/f or empty means False, otherwise it is True): ".format(message)
    ) not in ('N', 'n', 'F', 'f', '')

def _input(message: str, default: Optional[str] = None) -> Optional[str]:
    return input(message.format(default=default)).strip() or default

def _select_options(
        options: List[Any],
        header: Optional[str] = "Your options:",
        footer: str = "    Your choice? ",
        option_renderer: Callable[[Any], str] = str,
        accept_nonempty_string: bool = False,
) -> Union[Any, str]:
    assert options, "options must not be empty"
    if header:
        print(header)
    for i, o in enumerate(options, start=1):
        print("    {}: {}".format(i, option_renderer(o)))
    if accept_nonempty_string:
        print("    Or you can just type in your input.")
    while True:
        raw_data = input(footer)
        try:
            choice = int(raw_data)
            if 1 <= choice <= len(options):
                return options[choice - 1]
        except ValueError:
            if raw_data and accept_nonempty_string:
                return raw_data

enable_debug_log = _input_boolean("Enable MSAL Python's DEBUG log?")
logging.basicConfig(level=logging.DEBUG if enable_debug_log else logging.INFO)
try:
    from dotenv import load_dotenv
    load_dotenv()
    logging.info("Loaded environment variables from .env file")
except ImportError:
    logging.warning(
        "python-dotenv is not installed. "
        "You may need to set environment variables manually.")

def _input_scopes() -> List[str]:
    scopes = _select_options([
        "https://graph.microsoft.com/.default",
        "https://management.azure.com/.default",
        "User.Read",
        "User.ReadBasic.All",
    ],
        header="Select a scope (multiple scopes can only be input by manually typing them, delimited by space):",
        accept_nonempty_string=True
    ).split()  # Ensures scopes is a list of strings
    if "https://pas.windows.net/CheckMyAccess/Linux/.default" in scopes:
        raise ValueError("SSH Cert scope shall be tested by its dedicated functions")
    return scopes

def _select_account(app: msal.PublicClientApplication) -> Optional[Dict[str, str]]:
    accounts = app.get_accounts()
    if accounts:
        selected_account = _select_options(
            accounts,
            option_renderer=lambda a: "{}, came from {}".format(a.get("username", ""), a.get("account_source", "")),
            header="Account(s) already signed in inside MSAL Python:"
        )
        # Ensure selected_account is a dict before returning
        return selected_account if isinstance(selected_account, dict) else None
    else:
        print("No account available inside MSAL Python. Use other methods to acquire token first.")
        return None

def _acquire_token_silent(app):
    """acquire_token_silent() - with an account already signed into MSAL Python."""
    account = _select_account(app)
    if account:
        print_json(app.acquire_token_silent_with_error(
            _input_scopes(),
            account=account,
            force_refresh=_input_boolean("Bypass MSAL Python's token cache?"),
            auth_scheme=placeholder_auth_scheme
                if app.is_pop_supported() and _input_boolean("Acquire AT POP via Broker?")
                else None,
            ))

def _acquire_token_interactive(
    app: msal.PublicClientApplication,
    scopes: Optional[List[str]] = None,
    data: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    assert isinstance(app, msal.PublicClientApplication)
    scopes = scopes or _input_scopes()
    prompt_dict = _select_options([
        {"value": None, "description": "Unspecified. Proceed silently with a default account (if any), fallback to prompt."},
        {"value": "none", "description": "none. Proceed silently with a default account (if any), or error out."},
        {"value": "select_account", "description": "select_account. Prompt with an account picker."},
    ],
        option_renderer=lambda o: o["description"],
        header="Prompt behavior?"
    )
    prompt = prompt_dict.get("value") if isinstance(prompt_dict, dict) else None

    login_hint: Optional[str] = None
    if prompt != "select_account":
        raw_login_hint = _select_options(
            [None] + [a.get("username", "") for a in app.get_accounts()],
            header="login_hint? (If you have multiple signed-in sessions in browser/broker, and you specify a login_hint to match one of them, you will bypass the account picker.)",
            accept_nonempty_string=True
        )
        login_hint = raw_login_hint.get("username") if isinstance(raw_login_hint, dict) else raw_login_hint

    result = app.acquire_token_interactive(
        scopes,
        parent_window_handle=app.CONSOLE_WINDOW_HANDLE,
        enable_msa_passthrough=app.client_id in [_AZURE_CLI, _VISUAL_STUDIO],
        port=1234,
        prompt=prompt,
        login_hint=login_hint,
        data=data or {},
        auth_scheme=placeholder_auth_scheme
            if app.is_pop_supported() and _input_boolean("Acquire AT POP via Broker?")
            else None,
    )
    if result and isinstance(result, dict):
        id_token_claims = result.get("id_token_claims")
        if isinstance(id_token_claims, dict):  # Ensure id_token_claims is a dict before using get
            signed_in_user = id_token_claims.get("preferred_username")
            if signed_in_user != login_hint:
                logging.warning('Signed-in user "%s" does not match login_hint', signed_in_user)
        print_json(result)  # Only print if result is a dictionary
    return result if isinstance(result, dict) else None

def _acquire_token_by_username_password(app):
    """acquire_token_by_username_password() - See constraints here: https://docs.microsoft.com/en-us/azure/active-directory/develop/msal-authentication-flows#constraints-for-ropc"""
    print_json(app.acquire_token_by_username_password(
        _input("username: "), getpass.getpass("password: "), scopes=_input_scopes()))

def _acquire_token_by_device_flow(app):
    """acquire_token_by_device_flow() - Note that this one does not go through broker"""
    assert isinstance(app, msal.PublicClientApplication)
    flow = app.initiate_device_flow(scopes=_input_scopes())
    print(flow["message"])
    sys.stdout.flush()  # Some terminal needs this to ensure the message is shown
    input("After you completed the step above, press ENTER in this console to continue...")
    result = app.acquire_token_by_device_flow(flow)  # By default it will block
    print_json(result)

_JWK1 = """{"kty":"RSA", "n":"2tNr73xwcj6lH7bqRZrFzgSLj7OeLfbn8216uOMDHuaZ6TEUBDN8Uz0ve8jAlKsP9CQFCSVoSNovdE-fs7c15MxEGHjDcNKLWonznximj8pDGZQjVdfK-7mG6P6z-lgVcLuYu5JcWU_PeEqIKg5llOaz-qeQ4LEDS4T1D2qWRGpAra4rJX1-kmrWmX_XIamq30C9EIO0gGuT4rc2hJBWQ-4-FnE1NXmy125wfT3NdotAJGq5lMIfhjfglDbJCwhc8Oe17ORjO3FsB5CLuBRpYmP7Nzn66lRY3Fe11Xz8AEBl3anKFSJcTvlMnFtu3EpD-eiaHfTgRBU7CztGQqVbiQ", "e":"AQAB"}"""
_SSH_CERT_DATA = {"token_type": "ssh-cert", "key_id": "key1", "req_cnf": _JWK1}
_SSH_CERT_SCOPE = ["https://pas.windows.net/CheckMyAccess/Linux/.default"]

def _acquire_ssh_cert_silently(app: msal.PublicClientApplication) -> None:
    account = _select_account(app)
    if account:
        result = app.acquire_token_silent(
            _SSH_CERT_SCOPE,
            account,
            data=_SSH_CERT_DATA,
            force_refresh=_input_boolean("Bypass MSAL Python's token cache?"),
        )
        if result and isinstance(result, dict):
            print_json(result)
        if result and result.get("token_type") != "ssh-cert":
            logging.error("Unable to acquire an ssh-cert.")

def _acquire_ssh_cert_interactive(app: msal.PublicClientApplication) -> None:
    """Acquire an SSH Cert interactively - This typically only works with Azure CLI"""
    assert isinstance(app, msal.PublicClientApplication)
    result = _acquire_token_interactive(app, scopes=_SSH_CERT_SCOPE, data=_SSH_CERT_DATA)
    
    if result and result.get("token_type") != "ssh-cert":
        logging.error("Unable to acquire an ssh-cert")


_POP_KEY_ID = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA-AAAAAAAA'  # Fake key with a certain format and length
_RAW_REQ_CNF = json.dumps({"kid": _POP_KEY_ID, "xms_ksl": "sw"})
_POP_DATA = {  # Sampled from Azure CLI's plugin connectedk8s
    'token_type': 'pop',
    'key_id': _POP_KEY_ID,
    "req_cnf": base64.urlsafe_b64encode(_RAW_REQ_CNF.encode('utf-8')).decode('utf-8').rstrip('='),
        # Note: Sending _RAW_REQ_CNF without base64 encoding would result in an http 500 error
}  # See also https://github.com/Azure/azure-cli-extensions/blob/main/src/connectedk8s/azext_connectedk8s/_clientproxyutils.py#L86-L92

def _acquire_pop_token_interactive(app):
    """Acquire a POP token interactively - This typically only works with Azure CLI"""
    assert isinstance(app, msal.PublicClientApplication)
    POP_SCOPE = ['6256c85f-0aad-4d50-b960-e6e9b21efe35/.default']  # KAP 1P Server App Scope, obtained from https://github.com/Azure/azure-cli-extensions/pull/4468/files#diff-a47efa3186c7eb4f1176e07d0b858ead0bf4a58bfd51e448ee3607a5b4ef47f6R116
    result = _acquire_token_interactive(app, scopes=POP_SCOPE, data=_POP_DATA)
    if result and isinstance(result, dict):
        print_json(result)
        if result.get("token_type") != "pop":
            logging.error("Unable to acquire a pop token")

def _remove_account(app):
    """remove_account() - Invalidate account and/or token(s) from cache, so that acquire_token_silent() would be reset"""
    account = _select_account(app)
    if account:
        app.remove_account(account)
        print('Account "{}" and/or its token(s) are signed out from MSAL Python'.format(account["username"]))

def _acquire_token_for_client(app):
    """CCA.acquire_token_for_client() - Rerun this will get same token from cache."""
    assert isinstance(app, msal.ConfidentialClientApplication)
    result = app.acquire_token_for_client(scopes=_input_scopes())
    
    if result is not None and isinstance(result, dict):
        print_json(result)

def _remove_tokens_for_client(app):
    """CCA.remove_tokens_for_client() - Run this to evict tokens from cache."""
    assert isinstance(app, msal.ConfidentialClientApplication)
    app.remove_tokens_for_client()

def _exit(app):
    """Exit"""
    bug_link = (
        "https://identitydivision.visualstudio.com/Engineering/_queries/query/79b3a352-a775-406f-87cd-a487c382a8ed/"
        if app._enable_broker else
        "https://github.com/AzureAD/microsoft-authentication-library-for-python/issues/new/choose"
        )
    print("Bye. If you found a bug, please report it here: {}".format(bug_link))
    sys.exit()

def _main():
    print("Welcome to the Msal Python {} Tester (Experimental)\n".format(msal.__version__))
    cache_choice = _select_options([
            {
                "choice": "empty",
                "desc": "Start with an empty token cache. Suitable for one-off tests.",
            },
            {
                "choice": "reuse",
                "desc": "Reuse the previous token cache {} (if any) "
                    "which was created during last test app exit. "
                    "Useful for testing acquire_token_silent() repeatedly".format(
                        _token_cache_filename),
            },
        ],
        option_renderer=lambda o: o["desc"],
        header="What token cache state do you want to begin with?",
        accept_nonempty_string=False)
    if isinstance(cache_choice, dict) and cache_choice.get("choice") == "reuse" and os.path.exists(_token_cache_filename):
        try:
            global_cache.deserialize(open(_token_cache_filename, "r").read())
        except IOError:
            pass  # Use empty token cache
    chosen_app = _select_options(
        [
            {"client_id": _AZURE_CLI, "name": "Azure CLI (Correctly configured for MSA-PT)"},
            {"client_id": _VISUAL_STUDIO, "name": "Visual Studio (Correctly configured for MSA-PT)"},
            {"client_id": "95de633a-083e-42f5-b444-a4295d8e9314", "name": "Whiteboard Services (Non MSA-PT app. Accepts AAD & MSA accounts.)"},
            {
                "client_id": os.getenv("CLIENT_ID"),
                "client_secret": os.getenv("CLIENT_SECRET"),
                "name": "A confidential client app (CCA) whose settings are defined "
                         "in environment variables CLIENT_ID and CLIENT_SECRET",
            },
        ],
        option_renderer=lambda a: a["name"],
        header="Impersonate this app (or you can type in the client_id of your own public client app)",
        accept_nonempty_string=True,
    )

    # Initialize client_id and client_secret to None to avoid unbound errors
    client_id = None
    client_secret = None

    is_cca = isinstance(chosen_app, dict) and "client_secret" in chosen_app
    if is_cca and isinstance(chosen_app, dict):
        client_id = chosen_app.get("client_id")
        client_secret = chosen_app.get("client_secret")
        if not (client_id and client_secret):
            raise ValueError("You need to set environment variables CLIENT_ID and CLIENT_SECRET")

    enable_broker = (not is_cca) and _input_boolean(
        "Enable broker? (It will error out later if your app has not registered some redirect URI)"
    )
    enable_pii_log = _input_boolean("Enable PII in broker's log?") if enable_broker and enable_debug_log else False
    authority = _select_options(
        [
            "https://login.microsoftonline.com/common",
            "https://login.microsoftonline.com/organizations",
            "https://login.microsoftonline.com/microsoft.onmicrosoft.com",
            "https://login.microsoftonline.com/msidlab4.onmicrosoft.com",
            "https://login.microsoftonline.com/consumers",
        ],
        header="Input authority (Note that MSA-PT apps would NOT use the /common authority)",
        accept_nonempty_string=True,
    )

    instance_discovery = (
        _input_boolean(
            "You input an unusual authority which might fail the Instance Discovery. "
            "Now, do you want to perform Instance Discovery on your input authority?"
        )
        if authority and not authority.startswith("https://login.microsoftonline.com")
        else None
    )

    app = (
        msal.PublicClientApplication(
            client_id if client_id else chosen_app,
            authority=authority,
            instance_discovery=instance_discovery,
            enable_broker_on_windows=enable_broker,
            enable_broker_on_mac=enable_broker,
            enable_pii_log=enable_pii_log,
            token_cache=global_cache,
        )
        if not is_cca
        else msal.ConfidentialClientApplication(
            client_id,
            client_credential=client_secret,
            authority=authority,
            instance_discovery=instance_discovery,
            enable_pii_log=enable_pii_log,
            token_cache=global_cache,
        )
    )
    methods_to_be_tested = [
            _acquire_token_silent,
        ] + ([
            _acquire_token_interactive,
            _acquire_token_by_device_flow,
            _acquire_ssh_cert_silently,
            _acquire_ssh_cert_interactive,
            _acquire_pop_token_interactive,
            ] if isinstance(app, msal.PublicClientApplication) else []
        ) + [
            _acquire_token_by_username_password,
            _remove_account,
        ] + ([
            _acquire_token_for_client,
            _remove_tokens_for_client,
            ] if isinstance(app, msal.ConfidentialClientApplication) else []
        )
    while True:
        func = _select_options(
            methods_to_be_tested + [_exit],
            option_renderer=lambda f: f.__doc__, header="MSAL Python APIs:")
        try:
            if callable(func):
                func(app)
        except ValueError as e:
            logging.error("Invalid input: %s", e)
        except KeyboardInterrupt:  # Useful for bailing out a stuck interactive flow
            print("Aborted")

if __name__ == "__main__":
    _main()

