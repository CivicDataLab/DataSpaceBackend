# Metadata contract

These files are owned by DataSpaceBackend and are the source of truth for the
metadata export. Edit them here.

- `crosswalk.json` — the mapping: one entry per concept, and for each standard
  the property it becomes, its value type and obligation, plus the concepts the
  standard cannot carry (`gaps`). The engine in `../crosswalk.py` reads it and
  knows nothing about any standard by name.
- `licenses.csv`, `sectors.csv`, `geographies.csv` — allowed values with URIs.
  `alt_codes` carries `dataspace_enum=<our enum value>` for licences, which is
  how a platform value finds its row. Geographies cover regions, states, union
  territories and districts.

Changing a mapping decision means editing `crosswalk.json` in a PR, like any
other code. Adding a standard means adding a block under `standards`.

Origin: the first version was copied from CivicDataLab/DataSpace-data-ecosystem
at commit 83e577752784 (Sep 2026) and has been edited here since. There is no
runtime or build-time link to that repository.
