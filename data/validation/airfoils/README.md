# Airfoil coordinate files

One Selig-format `.dat` file per section, named `<name>.dat` (the `airfoil` parameter of family
airfoil2d is `<name>`; lower case letters, digits, `_` and `-`, up to 32 characters).

Each file is a retrieved file (record where it came from in the commit or docs that adds it), never
typed from memory. The sha256 of the file bytes is recorded in each run's `geometry.json` as
`section_sha256`.
