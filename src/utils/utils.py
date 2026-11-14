from typing import Optional

def get_str_value(
    cli_value: Optional[str],
    label: str,
    default: Optional[str]
) -> str:
    """
    Get a string value from the CLI input or prompt the user.

    Args:
        cli_value: The value provided via the command-line interface.
        label: The label to display when prompting the user.
        default: The default value to use if no CLI value is provided. If None, the user will be prompted.

    Returns:
        The resulting string value.
    """
    if cli_value is not None and cli_value.strip() != "":
        return cli_value

    if default is not None:
        return default
    
    while True:
        value = input(f"{label}: ").strip()
        if not value:
            print("This field is required.")
            continue
        return value

def get_int_value(
    cli_value: Optional[str],
    label: str,
    default: Optional[int]
) -> int:
    """
    Get an integer value from the CLI input or prompt the user.

    Args:
        cli_value: The value provided via the command-line interface.
        label: The label to display when prompting the user.
        default: The default value to use if no CLI value is provided. If None, the user will be prompted.

    Returns:
        The resulting integer value.
    """
    if cli_value is not None and cli_value.strip() != "":
        if not cli_value.isdigit():
            print(f"Invalid integer value for {label}: {cli_value}")
            exit(1)
        return int(cli_value)

    if default is not None:
        return default
    
    while True:
        value = input(f"{label}: ").strip()
        if not value:
            print("This field is required.")
            continue
        if not value.isdigit():
            print(f"Invalid integer value for {label}: {value}")
            continue
        return int(value)
