from typing import Optional

def get_str_value(cli_value: Optional[str], label: str, default: Optional[str]) -> str:
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

def get_int_value(cli_value: Optional[str], label: str, default: Optional[int]) -> int:
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
