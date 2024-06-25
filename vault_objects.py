"""Includes all vault base objects such as Entry and Vault"""

import logging
import json
import zipfile
from collections import defaultdict
from urllib.parse import urlparse
import argparse
from typing import (
    Dict,
    List,
    Literal,
    Tuple,
    Any,
    Optional,
    Union,
    List,
    Optional,
)
from collections import defaultdict
from urllib.parse import urlparse
from copy import deepcopy
from uuid import uuid4, UUID
import datetime

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

NAMESPACE = UUID()


# Subclasses for specific entry types (e.g., LoginEntry, CreditCardEntry, etc.)
class Entry:
    """Represents a generic entry in a password vault."""

    def __init__(self, item: Dict[str, Any]):
        self.instance_time = datetime.datetime.now()

        # Root keys
        self.item_dict: Dict[str, Any] = item
        self.item_id: str = item.get("id") or str(uuid4())
        self.name = item.get("name")
        self.data: Dict[str, Any] = item.get("data", {})
        self.state: int = item.get("state", 1)
        self.vault: str = item.get("vault")
        if create_time := item.get("create_time"):
            self.create_time = datetime.datetime(create_time)
        else:
            self.create_time = datetime.datetime.now()
        if mod_time := item.get("modify_time"):
            self.modify_time = datetime.datetime(mod_time)
        else:
            self.modify_time = datetime.datetime.now()
        self.favorite: bool = item.get("favorite", False)
        self.type: Literal["login", "credit_card", "note", "alias"] = self.data["type"]

    def __repr__(self):
        """Provides a string representation of the entry."""
        return f"Entry(item_id={self.item_id}, type={self.type}, name={self.name})"

    def __str__(self):
        return f"Entry(type={self.type}, name={self.name})"

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
        return name.title() if name and not "." in name else name

    def clean(self, clean_name=False):
        """Cleans URLs and name in a login entry."""
        if self.urls:
            self.urls = self.unique_list(
                [self.clean_url(url) for url in self.urls]
            )
        if clean_name and self.name:
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
        """Creates a dictionary representation of the entry for Proton Pass"""
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


class CreditCardEntry(Entry):
    """Represents a credit card entry in a password vault."""

    def __init__(self, entry_data: Dict[str, Any]):
        """Initializes a CreditCardEntry."""
        super().__init__(entry_data)

        content = self.data.get("content", {})  
        metadata = self.data.get("metadata", {})

        # Card-Specific Attributes
        self.cardholder_name: str = content.get("cardholderName")
        self.card_type: str = content.get("cardType")
        self.number: str = content.get("number")
        self.exp_date: str = content.get("expirationDate")
        self.pin: str = content.get("pin")
        self.code: str = content.get("code")  # CVV/CVC

        # Initialize other attributes from metadata
        self.name: str = metadata.get("name")
        self.note: str = metadata.get("note")
        self.uuid: str = metadata.get("itemUuid")

    def __hash__(self):
        """Hash based on card number and cardholder name."""
        return hash((self.number, self.cardholder_name))

    def __eq__(self, other):
        """Equality comparison based on hash."""
        return isinstance(other, CreditCardEntry) and hash(self) == hash(other)
 
    def clean(self):
        """Optional: Implement cleaning logic specific to credit card data."""
        pass

    def _merge_entry(self, other: "CreditCardEntry") -> None:
        """Merges two CreditCardEntry objects (assuming the same card)."""
        # Implement the merging logic here, e.g., prefer newer expiry date, combine notes, etc.
        # This is a basic example (replace with your actual logic):
        if self != other:
            raise ValueError(f"Unable to merge: {self} != {other}")

        sorted_entries = sorted((self, other), key=lambda x: x.modify_time)
        newer: "CreditCardEntry" = sorted_entries[-1]
        self.__dict__ = deepcopy(newer.__dict__)
        

    def to_dict(self) -> Dict[str, Any]:
        """Converts the CreditCardEntry object back to a dictionary."""
        return_dict = deepcopy(self.item_dict)  # Create a deep copy to avoid modifying original data
        return_dict["itemId"] = self.item_id
        return_dict["type"] = self.type
        return_dict["createTime"] = self.create_time
        return_dict["modifyTime"] = self.modify_time

        metadata = return_dict["data"]["metadata"]
        metadata["name"] = self.name
        metadata["note"] = self.note
        metadata["itemUuid"] = self.uuid

        content = return_dict["data"]["content"]
        content["cardholderName"] = self.cardholder_name
        content["cardType"] = self.card_type
        content["number"] = self.number
        content["expirationDate"] = self.exp_date
        content["code"] = self.code

        return return_dict

# Vault and VaultHandler objects that create a representation of vaults in this program. It managing the cleaning and processing of vaults once they are loaded in.
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
            "creditCard": CreditCardEntry,
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
                logging.info(
                    f"Found {len(entries)} duplicates of: {entries[0]}"
                )
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
        input_file: str,
        vault_names: Optional[List[str]] = None,
    ):
        self.input_file = input_file
        self.vault_names = vault_names
        self.vaults:List[Vault] = []

    def load_data(
        self, vault_format: Literal["protonpass", "csv", "bitwarden"]
    ) -> List[Vault]:
        """Cleans items in the vault (implementation varies by format)."""
        return VAULT_LOADERS[vault_format].load_data(self)

    def clean_vaults(self) -> List[Vault]:
        """Cleans items in the vault (implementation varies by format)."""
        for vault in self.vaults:
            vault.clean_items()
        return self.vaults

    def as_dict(self) -> Dict[str, Any]:
        """Returns this all the vaults as a single Proton Pass dict"""
        return {
            "encrypted": self.encrypted,
            "userId": self.user_id,
            "version": self.version,
            "vaults": {vault.id: vault.to_dict() for vault in self.vaults},
        }

    def deduplicate_in_vaults(self) -> List[Vault]:
        """Deduplicates items based on a unique key (implementation varies by format)."""
        for vault in self.vaults:
            vault.merge_duplicate_items()
        return self.vaults

    def save_data(
        self,
        output_filename: str,
        vault_format: Literal["protonpass", "csv", "bitwarden"],
    ) -> None:
        """Saves vault data to a file (implementation varies by format)."""
        return VAULT_SAVERS[vault_format].save_data(output_filename, self)


# VaultLoaders: Strategy ojects with static methods that load different password databases into a VaultHandler and Vault objects
class VaultLoader:
    """Superclass for different vault importers"""

    def load_data(self, vault_handler: VaultHandler) -> List[Vault]:
        """Loads vaults into a Vault Handler (implementation varies by format)."""
        raise NotImplementedError("Subclasses must implement load_vaults!")


class ProtonPassLoader(VaultLoader):
    """An object that handles importing Proton Pass zipfiles."""

    @staticmethod
    def load_data(vault_handler: VaultHandler) -> List[Vault]:
        """Loads data from a Proton Pass zip file and filters vaults."""
        vaults = []
        try:
            with zipfile.ZipFile(vault_handler.input_file, "r") as zf:
                # Directly access data.json within the "Proton Pass" folder
                with zf.open("Proton Pass/data.json", "r") as f:
                    data = json.load(f)
                for vault_id, vault_data in data["vaults"].items():
                    if (
                        not vault_handler.vault_names
                        or vault_data["name"] in vault_handler.vault_names
                    ):
                        vaults.append(
                            Vault(
                                vault_id,
                                vault_data.get("name"),
                                vault_dict=vault_data,
                            )
                        )
                vault_handler.raw_data = deepcopy(data)
                vault_handler.encrypted = data["encrypted"]
                vault_handler.user_id = data["userId"]
                vault_handler.version = data["version"]
                vault_handler.vaults = vaults
        except (zipfile.BadZipFile, KeyError) as e:
            raise ValueError(f"Invalid Proton Pass export file: {e}")
        return vault_handler.vaults


# VaultSavers: Strategy objects with static methods that export vaults to an external file.
class VaultSaver:
    @staticmethod
    def save_data(output_file: str, vault_handler: VaultHandler):
        """Saves vaults into a Vault Handler (implementation varies by format)."""
        raise NotImplementedError("Subclasses must implement save_data!")


class ProtonPassSaver(VaultSaver):

    @staticmethod
    def save_data(output_file: str, vault_handler: VaultHandler) -> None:
        """
        Saves the processed vault data back into a Proton Pass zip file (in UTF-8).
        Additionally, saves a copy of the data in a JSON file for debugging.
        """
        try:
            # Get the data to be written using as_dict()
            data_to_save = {}
            data_to_save["encrypted"] = vault_handler.encrypted
            data_to_save["userId"] = vault_handler.user_id
            data_to_save["version"] = vault_handler.version
            data_to_save["vaults"] = {}
            for vault in vault_handler.vaults:
                data_to_save["vaults"][vault.id]




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

            logging.info(
                f"Data saved to {output_file} and {debug_output_file}"
            )

        except Exception as e:
            raise ValueError(f"Error saving data: {e}")


    @staticmethod
    def convert_entry(entry: Entry) -> dict[str, Any]:
        """Converts an Entry object to a dictionary compatible with Proton Pass."""
        entry_data = deepcopy(vars(entry))
        entry = {}

        entry["itemId"] = entry_data.get("item_id", str(uuid4()))
        entry["shareId"] = entry_data.get("share_id", str(uuid4()))
        entry["state"] = entry_data.get("state" or 1)
        entry["aliasEmail"] = entry_data.get("alias_email", None)
        entry["contentFormatVersion"] = entry_data.get("content_format_version", 4)
        entry["createTime"] = entry_data.get("create_time", int(datetime.datetime.now().timestamp()))
        entry["modifyTime"] = entry_data.get("modify_time", int(datetime.datetime.now().timestamp()))
        entry["favorite"] = entry_data.get("favorite", False)

        entry["data"] = {}
        
        if entry_data["entry_type"] == "login":
            entry["data"]["urls"] = entry_data.get("url", [])
            entry["data"]["username"] = entry_data.get("username", None)
            entry["data"]["password"] = entry_data.get("password", None)

        return entry
    
    @staticmethod
    def get_login_data(entry_data: Dict[str, Any]):
        """Extracts login data from an Entry object."""
        entry_data: Dict[str, Any] = entry_data["data"]
        metadata = {}
        login_data = {}
        login_data["metadata"] = {}
        entry_metadata = entry_data.get("metadata", {})
        metadata["name"] = entry_metadata.get("name", [])
        metadata["note"] = entry_metadata.get("metadata", {}).get("username", None)
        metadata["itemUuid"] = entry_metadata.get("metadata", {}).get("item_uuid", str(uuid4().node)[:8])


def main(
    input_file: str,
    output_file: str,
    format_str: str,
    vault_names: Optional[Union[str, List[str]]] = None,
):
    """Main function to load, clean, deduplicate, and save password data."""
    try:
        processor = VaultHandler(input_file, vault_names)
        processor.load_data(format_str)
        processor.clean_vaults()
        processor.deduplicate_in_vaults()
        processor.save_data(output_file, format_str)
    except (zipfile.BadZipFile, FileNotFoundError, ValueError, KeyError) as e:
        logging.error(f"Error processing file: {e}")


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

VAULT_LOADERS = {
    "protonpass": ProtonPassLoader,
}

VAULT_SAVERS = {
    "protonpass": ProtonPassSaver,
}

