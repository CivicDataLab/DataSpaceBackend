"""Match saved publication author names to platform users.

Until #560 the publication wizard picked real users but saved only their display
name in ``Publication.authors``. These helpers turn such a name back into a user
id: used by the one-time data migration and by the read-only
``unlinked_publication_authors`` command. Pure functions over plain values, so the
migration can feed them rows from its historical models.
"""

from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# (user id, first name, last name, username)
UserRow = Tuple[int, Optional[str], Optional[str], Optional[str]]


def display_name(
    first_name: Optional[str], last_name: Optional[str], username: Optional[str]
) -> str:
    """The name the frontend saved: same rule as ``TypeUser.full_name``."""
    if first_name and last_name:
        return f"{first_name} {last_name}"
    if first_name:
        return first_name
    if last_name:
        return last_name
    return username or ""


def name_key(name: Optional[str]) -> str:
    """Compare names ignoring case and extra spaces."""
    return " ".join((name or "").split()).casefold()


def index_users(rows: Iterable[UserRow]) -> Dict[str, List[int]]:
    """Map each display-name key to the ids of every user who has it."""
    index: Dict[str, List[int]] = {}
    for user_id, first_name, last_name, username in rows:
        key = name_key(display_name(first_name, last_name, username))
        if key:
            index.setdefault(key, []).append(user_id)
    return index


def index_members(rows: Iterable[Tuple[int, int]]) -> Dict[int, Set[int]]:
    """Map each organisation id to its member user ids, from (user, org) pairs."""
    members: Dict[int, Set[int]] = {}
    for user_id, organization_id in rows:
        members.setdefault(organization_id, set()).add(user_id)
    return members


def match_author(
    name: str,
    index: Dict[str, List[int]],
    owner_id: Optional[int],
    org_member_ids: Set[int],
) -> Optional[int]:
    """The one user a saved name stands for, or None.

    Several users with the same name are never guessed between: the
    publication's owner wins, then a single member of its organisation;
    otherwise the name stays unlinked.
    """
    candidates = index.get(name_key(name), [])
    if len(candidates) == 1:
        return candidates[0]
    if owner_id is not None and owner_id in candidates:
        return owner_id
    members = [user_id for user_id in candidates if user_id in org_member_ids]
    if len(members) == 1:
        return members[0]
    return None


def split_authors(
    names: Sequence[str],
    index: Dict[str, List[int]],
    owner_id: Optional[int],
    org_member_ids: Set[int],
) -> Tuple[List[int], List[str]]:
    """Linked user ids (each once) and the names that matched nobody."""
    linked: List[int] = []
    unlinked: List[str] = []
    for name in names:
        if not name_key(name):
            continue
        user_id = match_author(name, index, owner_id, org_member_ids)
        if user_id is None:
            unlinked.append(name)
        elif user_id not in linked:
            linked.append(user_id)
    return linked, unlinked
