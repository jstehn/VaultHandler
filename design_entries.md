
**Design Document: VaultHandler Entry Objects**

**1. Introduction**

This document outlines the design and implementation of Python objects representing entries in various password management systems. These objects provide a structured and Pythonic way to interact with entry data, allowing for easy manipulation, validation, cleaning, and merging. The design aims to be flexible and extensible to accommodate different password managers and potential schema changes.

**2. Object Hierarchy**



* **Entry (Base Class):**
    * Represents the fundamental properties shared by all Proton Pass entries.
    * Attributes:
        * item_id (str): Unique identifier (string). Defaults to a UUID4
        * name (str): A name for the Entry. Defaults to empty string.
        * orig_data (dict): A deep copy of the original entry_data dictionary.
        * data (dict): Dictionary containing entry-specific data. Defaults to empty dict and does not populate.
        * create_time (datetime): Datetime of creation. Defaults to instantiation time.
        * mod_time (datetime): Datetime of last modification. Defaults to instantiation time.
        * note (str): Notes or description about the entry. Defaults to None
        * favorite (boolean): Boolean indicating if the entry is pinned/favorite. Defaults to False
        * type (str): String indicating object type. Defaults to None
        * extra_fields (Dict): Designated spots for any extra data that is unique to the password manager. Defaults to empty dictionary.
        * entry_id (Tuple[str]): When this attribute is referenced, it should return an immutable tuple of the strings for item_id, name, type using the @proptery feature in python.
    * Methods:
        * __init__(self, entry_data: Dict[str, Any]): Constructor to initialize from JSON data.
        * __repr__(self) -> str: Returns a reasonable repr string that can represent the entry including its item_id, type, and name.
        * __str__(self) -> str: Returns a reasonable human readable str that has the item name and its type.
        * equals(self, other) -> str: Returns True if the two items are the same object type and have matching entry_id.
        * merge(self, other: Entry): Checks to see if the two entries are the same type. If they are not, it raises a TypeError. It then calls _merge_entry with the most recently modified Entry as the calling object and the older object as the other Entry. In ties, it picks arbitrarily.
        * unique_list(lst: List) -> List (Static Method): Returns a unique list while preserving order. In the event that it is an unhashable object such as a dictionary, it compares the two dictionaries to see if they have the same values recursively. If they do not have the same values, they can be seen as unique items and both are retained in the list.
    * Methods to be implemented by subclasses
        * _merge_entry(self, other: Entry) -> None: A placeholder method that mutatively merges two entries of the same type, changing the Entry that called the method. By default, it should start with the 
        * clean(self) -> None: Mutatively cleans the Entry.
        * 
* **LoginEntry (Subclass of Entry):**
    * Represents login credentials.
    * Additional Attributes:
        * username (string)
        * password (string)
        * name (string, optional): Website or service name.
        * totp (string, optional): TOTP URI
        * urls (list of strings, optional): Defaults to empty list
        * passkeys (list of dictionaries)
    * Additional Methods:
        * clean_url(url: str) [static method] -> str: Cleans and normalizes a URL.
        * clean_name(name:str) [static method] -> str: Cleans and standardizes a name. Does not alter capitalization.
        * clean(self): Applies cleaning to URLs.
        * _merge_entry(self, other: Entry) -> None: Merges two login objects. It goes through all attributes and merges the two entries. In dictionaries, it prefers the value in self it is something like a str, int, datetime, or boolean. If there are nested dicts, it recursively merges those dictionaries as well. In lists, it makes sure that the lists only have unique items as per the unique_list function.
* **CreditCard (Subclass of Entry):**
    * Represents credit card information.
    * Additional Attributes:
        * cardholder_name (string)
        * card_type (integer)
        * number (string)
        * verification_number (string)
        * expiration_date (string)
        * pin (string)
* **Note (Subclass of Entry):**
    * Represents a generic note entry.
    * Additional Attributes:
        * title (string, optional)
        * body (string)
* **Alias (Subclass of Entry):**
    * Represents an email alias.
    * No additional attributes beyond the base Entry class.

**3. entry_data schema**

The entry_data dictionary is something that is supplied into the Entry init to set the entry information. It follows the following format:

``` python
{
    "item_id": "str",
    "create_time": "str",
    "mod_time": "str",
    "favorite": "bool",
    "note": "str",
    "type": "str",
    "data": {
        # Contains the unique data to each entry type
    },
    "extra_fields": {
        # Contains the extra fields to each entry type
    }    
}
```

**4. Data Validation and Cleaning**



* Each subclass will have methods to validate and clean its specific data attributes according to the schema.
* The _merge_entry method in LoginEntry will handle merging logic for combining entries.

**5. Flexibility and Extensibility**



* The base Entry class allows for easy addition of new entry types in the future.
* Attributes can be added or modified in subclasses to accommodate changes in schema.

**6. Example Usage**


``` python

login_data = { \
    # ... (JSON data for a login entry) \
} \
login_entry = LoginEntry(login_data) \
login_entry.clean() \
    # ... (Further processing or analysis of the login entry) \
```


**Note:** This design document provides a high-level overview. Implementation details might vary depending on specific requirements and coding practices.
