"""Includes all vault base objects such as Entry and Vault"""

import json
import zipfile
from collections import defaultdict
from urllib.parse import urlparse
import argparse
from typing import Dict, List, Tuple, Any, Optional, Union, List, Optional
from collections import defaultdict
from urllib.parse import urlparse
from copy import deepcopy


class Entry:
    """Represents a generic entry in a password vault."""

    def __init__(self, item: Dict[str, Any]):
        self.item_dict = item
        self.item_id = item.get("itemId")
        self.data = item.get("data", {})
        self.name = self.data.get("metadata").get("name")

        self.pinned = item.get("pinned", False)
        self.type = self.data.get("type")
        self.create_time = item.get("createTime")
        self.modify_time = item.get("modifyTime")
        self.state = item.get("state", 1)
        self.alias_email = item.get("aliasEmail", None)

    def __repr__(self):
        """Provides a string representation of the entry."""
        return f"Entry(item_id={self.item_id}, type={self.type}, name={self.name})"

    def clean(self):
        """Placeholder for cleaning specific entry types."""
        raise NotImplementedError("Subclass must implement clean!")

    def to_dict(self) -> Dict[str, Any]:
        """Converts the entry back to a dictionary format."""
        raise NotImplementedError("Subclass must implement to_dict!")

    def _merge_entry(self, other_entry: "Entry") -> None:
        """Placeholder for merging entries of the same type."""
        raise NotImplementedError(
            "Merging not implemented for this entry type."
        )

    def unique_list(
        self,
        lst: List[Union[str, float, int]],
    ) -> List[Union[str, float, int]]:
        """Returns a unique list of strings, floats, or integers while preserving order."""
        seen = set()
        return [x for x in lst if not (x in seen or seen.add(x))]

    def clean_name(name: Optional[str]) -> Optional[str]:
        """Cleans item names (title case for websites, handles None)."""
        return name.title() if name and not urlparse(name).scheme else name

    def merge(self, other_entry: "Entry") -> None:
        """
        Merges this entry with another entry of the same type.

        Args:
            other_entry: The other Entry object to merge with.

        Raises:
            TypeError: If the other entry is not of the same type.
        """
        if not isinstance(other_entry, type(self)):
            raise TypeError("Cannot merge entries of different types.")

        # Call the subclass-specific merge implementation
        self._merge_entry(other_entry)


# Subclasses for specific entry types (e.g., LoginEntry, CreditCardEntry, etc.)
class LoginEntry(Entry):
    """Represents a login entry."""

    def __init__(self, entry_data: Dict[str, Any]):
        """
        Initializes a LoginEntry. If another LoginEntry is provided, it merges their data.
        """
        super().__init__(entry_data)

        content: Dict[str, Any] = self.data.get("content", {})
        metadata: Dict[str, Any] = self.data.get("metadata", {})

        # Initialize fields from nested dictionaries
        self.username: str = content.get("username")
        self.password: str = content.get("password")
        self.name: str = metadata.get("name")
        self.note: str = metadata.get("note")
        self.totp: str = content.get("totpUri", "")
        self.urls: List[str] = content.get("urls", [])
        self.passkeys: List[Dict[str, Any]] = content.get("passkeys", [])

    def __hash__(self):
        """Hash based on name, username, and password."""
        return hash((self.type, self.name, self.username, self.password))

    def __eq__(self, other):
        """Equality comparison based on hash."""
        return isinstance(other, LoginEntry) and hash(self) == hash(other)

    def clean_url(self, url: str) -> str:
        """Cleans URLs to their base form."""
        parsed_url = urlparse(url)
        return (
            f"{parsed_url.scheme}://{parsed_url.netloc}/"
            if parsed_url.scheme
            else url
        )

    def clean_name(self, name: Optional[str]) -> Optional[str]:
        """Cleans item names (title case for websites, handles None)."""
        return name.title() if name and not urlparse(name).scheme else name

    def clean(self):
        """Cleans URLs and name in a login entry."""
        if self.urls:
            self.urls = self.unique_list(
                [self.clean_url(url) for url in self.urls]
            )
        if self.name:
            self.name = self.clean_name(self.name)

    def _merge_entry(self, other: "LoginEntry") -> None:
        """Merges two LoginEntry objects."""
        if self != other:
            raise ValueError(f"Unable to merge: {self} != {other}")
        else:
            sorted_entries = sorted((self, other), key=lambda x: x.modify_time)
            older: "LoginEntry" = sorted_entries[0]
            newer: "LoginEntry" = sorted_entries[1]
            self.urls = self.unique_list(self.urls + other.urls)
            seen = set()
            self.passkeys = [
                passkey
                for passkey in (
                    self.data.get("passkeys", [])
                    + other.data.get("passkeys", [])
                )
                if not (
                    passkey.get("keyId") in seen
                    or seen.add(passkey.get("keyId"))
                )
            ]
            self.data["extraFields"] = self.data.get(
                "extraFields", []
            ) + other.data.get("extraFields", [])
            self.pinned = newer.pinned
            self.modify_time = newer.modify_time
            self.item_id = newer.item_id

    def to_dict(self) -> Dict[str, Any]:
        return_dict = deepcopy(self.item_dict)
        return_dict["itemId"] = self.item_id
        return_dict["type"] = "login"
        return_dict["createTime"] = self.create_time
        return_dict["modifyTime"] = self.modify_time
        return_dict["pinned"] = self.pinned
        return_dict["aliasEmail"] = self.alias_email

        metadata = return_dict["data"]["metadata"]
        metadata["name"] = self.name
        metadata["note"] = self.note

        content = return_dict["data"]["content"]
        content["username"] = self.username
        content["password"] = self.password
        content["urls"] = self.urls
        content["totpUri"] = self.totp
        content["passkeys"] = self.passkeys

        return return_dict


class Vault:
    """Represents a password vault."""

    def __init__(
        self,
        id: str,
        name: str,
        items: Optional[List[Entry]] = None,
        vault_dict: Dict[str, Any] = None,
    ):
        self.id = id
        self.name = name
        self.items = items or []
        self.vault_dict = vault_dict or dict()
        for item in vault_dict.get("items", []):
            entry = self._create_entry(item)
            if entry:
                self.items.append(entry)

    def _create_entry(self, item_data: Dict[str, Any]) -> Entry:
        """Creates the appropriate Entry subclass based on the item type."""
        entry_type = item_data.get("data", {}).get("type")
        entry_classes = {
            "login": LoginEntry,
        }
        entry_constructor = entry_classes.get(entry_type)
        if entry_constructor:
            return entry_constructor(item_data)
        else:
            return None

    def clean_items(self):
        """Cleans all items in the vault."""
        for item in self.items:
            item.clean()

    def merge_duplicate_items(self) -> None:
        """Merges duplicate items in the vault in place."""
        seen_items = defaultdict(list)  # Store entries by their unique key

        # Group entries by their type and hash
        for entry in self.items:
            seen_items[(type(entry), hash(entry))].append(entry)

        # Merge duplicates and update items
        self.items = []  # Clear out the existing items
        for _, entries in seen_items.items():
            if len(entries) > 1:
                print(f"Found {len(entries)} duplicates of: {entries[0]}")
                merged_entry = entries[0]  # Start with the first entry
                for other_entry in entries[1:]:
                    merged_entry.merge(other_entry)
            else:
                merged_entry = entries[0]
            self.items.append(merged_entry)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.vault_dict.get("description", ""),
            "display": self.vault_dict.get("display", {"color": 2, "icon": 2}),
            "items": [item.to_dict() for item in self.items],
        }


class VaultHandler:
    """Base class for handling vault data in different formats."""

    def __init__(
        self,
        data_file_path: str,
        vault_names: Optional[List[str]] = None,
    ):
        self.data_file_path = data_file_path
        self.vault_names = vault_names
        self.load_data()

    def load_vaults(self) -> List[Vault]:
        """Cleans items in the vault (implementation varies by format)."""
        raise NotImplementedError("Subclasses must implement load_vaults!")

    def clean_vaults(self) -> List[Vault]:
        """Cleans items in the vault (implementation varies by format)."""
        for vault in self.vaults:
            vault.clean_items()
        return self.vaults

    def deduplicate_in_vaults(self) -> List[Vault]:
        """Deduplicates items based on a unique key (implementation varies by format)."""
        for vault in self.vaults:
            vault.merge_duplicate_items()
        return self.vaults

    def save_data(self, output_filename: str) -> None:
        """Saves vault data to a file (implementation varies by format)."""
        raise NotImplementedError("Subclasses must implement save_data!")


class ProtonPassVaultHandler(VaultHandler):
    """Handles Proton Pass JSON vault data."""

    def __init__(
        self,
        data_file_path,
        vault_names: Optional[Union[str, List[str]]] = None,
    ):
        super().__init__(data_file_path, vault_names)

    def load_data(self) -> List[Vault]:
        """Loads data from a Proton Pass zip file and filters vaults."""
        vaults = []
        try:
            with zipfile.ZipFile(self.data_file_path, "r") as zf:
                # Directly access data.json within the "Proton Pass" folder
                with zf.open("Proton Pass/data.json", "r") as f:
                    data = json.load(f)
                for vault_id, vault_data in data["vaults"].items():
                    if (
                        not self.vault_names
                        or vault_data["name"] in self.vault_names
                    ):
                        vaults.append(
                            Vault(
                                vault_id,
                                vault_data.get("name"),
                                vault_dict=vault_data,
                            )
                        )
                self.raw_data = deepcopy(data)
                self.encrypted = data["encrypted"]
                self.user_id = data["userId"]
                self.version = data["version"]
                self.vaults = vaults
        except (zipfile.BadZipFile, KeyError) as e:
            raise ValueError(f"Invalid Proton Pass export file: {e}")
        return self.vaults

    def as_dict(self) -> Dict[str, Any]:
        return {
            "encrypted": self.encrypted,
            "userId": self.user_id,
            "version": self.version,
            "vaults": {vault.id: vault.to_dict() for vault in self.vaults},
        }

    def save_data(self, output_file: str) -> None:
        """
        Saves the processed vault data back into a Proton Pass zip file (in UTF-8).
        Additionally, saves a copy of the data in a JSON file for debugging.
        """
        try:
            # Get the data to be written using as_dict()
            data_to_save = self.as_dict()

            # Create the output zip file
            with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
                # Create the "Proton Pass" directory within the zip
                zf.writestr("Proton Pass/", "")
                # Write the JSON data to "Proton Pass/data.json" in UTF-8
                json_string = json.dumps(
                    data_to_save, indent=4, ensure_ascii=False
                )  # Create JSON string
                json_bytes = json_string.encode(
                    "utf-8"
                )  # Encode the string as UTF-8 bytes
                zf.writestr(
                    "Proton Pass/data.json", json_bytes
                )  # Write the bytes to the zip file

            # Save a copy as a JSON file in the working directory (for debugging)
            debug_output_file = "deduped_data.json"
            with open(debug_output_file, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, indent=4, ensure_ascii=False)

            print(f"Data saved to {output_file} and {debug_output_file}")

        except Exception as e:
            raise ValueError(f"Error saving data: {e}")


def main(
    input_file: str,
    output_file: str,
    format_str: str,
    vault_names: Optional[Union[str, List[str]]] = None,
):
    """Main function to load, clean, deduplicate, and save password data."""
    try:
        format_strategy_class = {
            "protonpass": ProtonPassVaultHandler,
            # "csv": CSVVaultHandler,
            # "bitwarden": BitwardenVaultHandler,
        }[format_str]
        processor = format_strategy_class(input_file)

        processor.load_data()
        processor.clean_vaults()
        processor.deduplicate_in_vaults()
        processor.save_data(output_file)
    except (zipfile.BadZipFile, FileNotFoundError, ValueError, KeyError) as e:
        print(f"Error processing file: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Deduplicate password data in various formats."
    )
    parser.add_argument(
        "input_file", help="The input file (ZIP, CSV, or JSON)"
    )
    parser.add_argument(
        "output_file", help="The output file (ZIP, CSV, or JSON)"
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["protonpass", "csv", "bitwarden"],
        required=True,
        help="The format of the input file",
    )
    parser.add_argument(
        "-v",
        "--vaults",
        nargs="+",
        metavar="vault_name",
        help="Vaults to include (optional, default is all)",
    )

    args = parser.parse_args()

    main(args.input_file, args.output_file, args.format, args.vaults)
