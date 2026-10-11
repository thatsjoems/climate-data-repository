# Ward and district names: repository list against NBS

Two lists name the places of Tanzania: the repository's own list (`backend/app/data/tanzania_geography.json`, the one users pick from in the
template) and the National Bureau of Statistics file of 2022 ward boundaries (`tanzania_ward_boundaries.json.gz`, used to check coordinates).
They come from different sources, so a few names are spelled differently. This page says how many, and what has been done and what has not.

## Districts

Both lists have **150 districts**, with the same names. The repository's list used to show 151: the extra one was a lower-case `korogwe` with
one ward, Manundu, which Korogwe already holds with the same village (Mbeza). It was a data-entry duplicate; it showed Korogwe twice in the
district list. It was removed on 11 October 2026 (the list now has 150 districts, 4,341 wards, 19,945 villages), and a test
(`test_geo_lookup.py`) stops two districts that differ only by capitals or spacing from coming back. The Concept Note's "151" can be taken
as 150 unless NBS says a district was created after the 2022 census; that is the one question left for the Bank (item 10 of
the request to the Bank).

## Wards

Compared inside each district, ignoring capitals, spaces and punctuation, and treating a bracket ("Mkindo (Kanindo)") as an alias:
**27 ward names in the repository's list have no identical name in the NBS file.** Every one has a close NBS spelling, listed as a suggestion in
`docs/WARD_NAME_DIFFERENCES.csv` (columns: region, district, repository name, NBS name, similarity). Most are one or two letters
(Oldeani / Oldean, Kitangari / Kitangali, Ugalla / Ugala); a few are further apart (Mahenge Mjini / Mahenge, Kibungo / Kibungo Juu,
Zawiani / Zuwiyani) and need a person who knows the place.

**What the system does today.** Nothing is corrected automatically. A row that names one of these wards is still checked: the coordinate check
accepts a clear near-match (this covers most of the 27) and otherwise checks the point against the district. At most **9** of the 27 are not
found by that near-match; they are listed in `COORDINATE_VALIDATION.md`.

**What is for the Bank to decide.** Which spelling is official for each of the 27 (the Census file, or the Bank's own usage), so that the
template's drop-down and the boundary file agree. Until then the drop-down keeps the repository's spelling.

Regenerate the CSV after any change to either list: `python backend/scripts/name_differences.py --csv docs/WARD_NAME_DIFFERENCES.csv`.
