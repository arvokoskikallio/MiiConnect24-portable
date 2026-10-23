# MiiConnect24 Portable — getting started

MiiConnect24 Portable helps you investigate Mario Kart Wii player identities, especially **NinRankings Top1000 profiles**. Give it a Top1000 profile and it reads that profile’s local Mii files, then looks for matching client IDs in other Top1000 profiles, the CTGP dump and the NinRankings Ghost Database dump. A **client ID** is an identifier stored inside a Mii.

A match is a useful lead, **not proof that the profiles belong to the same person**. Miis can be shared or copied, and someone can set a time on another player’s console.

The program runs in a text window. You do not need to know how to program. Follow the Windows instructions below in order.

## 1. Install Python

Python is the software that runs this tool.

1. Go to [python.org/downloads](https://www.python.org/downloads/) and install Python **3.10 or newer** for Windows.
2. If the installer offers **Add Python to PATH**, enable it.
3. Finish the installation.

You do not need to install any additional Python packages.

## 2. Make a folder for the program

1. Create a folder on your Desktop called **MiiConnect24 Portable**.
2. Download **MiiConnect24_Portable.zip** from the release/download post accompanying this guide.
3. Right-click the ZIP and choose **Extract All**.
4. Put the extracted **`mii_client_check.py`** and **`README.md`** directly inside your **MiiConnect24 Portable** folder.

Run the extracted program, not the copy inside the ZIP. Keep everything in this folder for the following steps.

## 3. Download the data it will search

The tool needs local copies of the profiles and ghosts it compares. These are called **dumps**: saved collections of data, not programs you need to install.

For the complete setup, collect these **four data inputs**. The first two enable the main Top1000 feature; the other two provide the additional CTGP and Ghost Database comparisons.

| Download or file | After downloading |
| --- | --- |
| [All Miis on the NinRankings Top1000 page](https://mega.nz/file/PVxQDaYT#9uJQikdQXdec-5HYZ82Ewq9U0izBR_es9JhwlEgkY6c), thanks to **Sean/FrostMoon** | Extract the `.mii` files. Put them in a folder named **`miis`** inside your program folder. Keep every filename unchanged, including Japanese characters, spaces and suffixes. |
| **Top1000 PID-to-Mii-filename JSON** | Obtain the mapping supplied by the project distributor and save it beside the script as **`ninrankings_pids.json`**. It tells the program which local Mii files belong to each Top1000 profile. |
| [CTGP Ghost Database dump — mid-2025](https://mega.nz/file/O9QRAY6S#WaC2vQYIH06vVKidOBGAmkbbKgHtOn24coJeyt8z-QA) | Extract it. Put the folder containing the profile `.json` files inside your program folder and name that folder **`ctgp_profiles`**. |
| [NinRankings Ghost Database dump — 8 November 2020](https://mega.nz/file/Oc4jyYoB#1S2JJhSE9HKmWrnOdKicaMcupbwxAdyAWSvEGWqvpas) | Extract it. Put the folder containing the ghost `.rkg` files inside your program folder and name that folder **`ninrankings`**. |

**The Top1000 Mii files and the PID mapping are both required.** The Mii files alone do not tell Portable which Top1000 profile they belong to. The mapping is a JSON file, not a spreadsheet or a client-ID listing. If the download does not include it, get that file from the distributor before continuing; you do not need to write it yourself.

If Windows cannot extract the archive, use an archive extractor such as [7-Zip](https://www.7-zip.org/). Make sure you have room for the extracted files as well as the downloads.

**Check your folder before continuing:**

- **MiiConnect24 Portable** contains `mii_client_check.py` and `README.md`.
- Beside the script, **`ninrankings_pids.json`** is the Top1000 profile-to-Mii mapping.
- **miis** contains the extracted Top1000 `.mii` files.
- **ctgp_profiles** contains lots of CTGP `.json` files.
- **ninrankings** contains lots of Ghost Database `.rkg` files.

Subfolders inside the data folders are fine. Do not rename the individual Mii, JSON or ghost files. If Windows hides extensions, enable **File name extensions** in File Explorer so you can check the filenames.

The CTGP and Ghost Database dumps are historical snapshots, so they do not include everything uploaded since their dates. Without either dump, comparisons against that collection are unavailable; complete the setup above to search all three sources.

## 4. Start MiiConnect24 Portable

1. Open your **MiiConnect24 Portable** folder in File Explorer.
2. Click the address bar at the top of File Explorer.
3. Type **`powershell`** and press Enter. A command window opens in that folder.
4. Copy this command into that window and press Enter:

```powershell
python mii_client_check.py
```

If Windows says it cannot find `python`, try:

```powershell
py mii_client_check.py
```

### The first start takes longer

The program reads your dump folders and prepares a searchable copy. Progress messages show how many files it has checked, any errors and an estimated time remaining. Let it finish; large collections can take a while.

Top1000 files are checked when you make the first search. You may also see **Local Top1000 Miis: ... profiles checked**; let that finish before expecting results.

It creates a folder called **`mii_client_check_cache`**. **Keep this folder.** On later launches, the program reuses it instead of reading every dump file again. You do not need to download or create a database yourself.

When preparation finishes, you will see a menu asking for **Choice:**.

## 5. Try your first search

Start with a **NinRankings Top1000 profile**:

1. Open the player’s Top1000 profile in your browser and copy its address. It should contain **`/mkwii/profil.php?id=`**, for example `https://ninrankings.org/mkwii/profil.php?id=477729692`.
2. In the program, type **`3`** at **Choice:** and press Enter.
3. Paste the Top1000 profile address at the next prompt and press Enter. You can also enter just its numeric profile ID.
4. The program finds that profile’s Mii filenames in `ninrankings_pids.json`, reads the corresponding files in `miis`, and checks their client IDs against the other data.
5. On the first search, wait while it prepares the Top1000 comparisons. It will then print the matching profiles and example ghosts.

It does **not** need to fetch the Top1000 page: the profile-to-Mii mapping and Mii files are local. If it says the PID is missing or no Mii files can be read, check the two Top1000 inputs from step 3.

**Top1000 and Ghost Database profiles are different.** Option 3 accepts `/mkwii/profil.php` addresses. For a `/ghostdatabase/profil.php?id=` address instead, choose **4** and enter `dec:` followed by the number from that address.

You can search again when the menu returns. There is no need to close and reopen the program between searches.

### The other menu choices

| Type | Use it for |
| --- | --- |
| **1** | A Chadsoft player profile. Paste its profile address, enter its 16-character profile ID, or enter the path to a local profile JSON file. |
| **2** | A ghost or Mii you already have. Enter the full path to a `.rkg` or Wii `.mii` file, or paste a direct ghost download address. Chadsoft ghost-viewer addresses work too. |
| **3** | The main Top1000 lookup: paste a NinRankings **Top1000** profile address or enter its numeric PID. Uses `ninrankings_pids.json` and the `miis` folder. |
| **4** | A client ID you already know. Enter eight hexadecimal characters, such as `0463AAEA`. For a decimal number, explicitly enter `dec:73640682`. |
| **q** | Quit the program. |

An empty profile/file input cancels that search. For a file path, you can copy it from File Explorer using **Copy as path** and paste it into the program.

## 6. Understand a match

The results show the Miis found in your input, followed by matching CTGP and NinRankings profiles. Profile and example-ghost addresses are printed so you can copy them into your browser.

- **Same client ID:** the Miis share an origin identifier. Investigate the names, profiles and example ghosts before drawing a conclusion.
- **“This Mii appears on both sides”:** the same Mii/avatar ID also appears in your input. It is an ID comparison, not a visual face comparison.
- **Several names under one Mii:** the tool observed those names with the same Mii ID. It shows an example ghost for that group.
- **Filename/name candidates:** duplicate names prevented the mapping from identifying one file. The tool checks the possible files, but matches from those files do not confirm ownership of the requested Top1000 profile.
- **No matches:** nothing eligible was found in your supplied data. It does not mean no other profile exists.

The input CTGP profile is left out of its own results. Generic blank, `Player` and `no name` Miis, placeholder client IDs and client IDs associated with default Miis in the comparison data are excluded to avoid misleading matches.

The program does not assign players, edit identities or upload anything to MKWLeaderboards.

## 7. Stop and return later

Type **`q`** at the menu to quit. To return, repeat step 4.

If you need to stop while the initial data preparation is running, press **Ctrl+C**. Completed work is saved; running the same command again resumes preparation.

If you later add, replace or remove dump files, ask the program to check the folders again:

```powershell
python mii_client_check.py --refresh-index
```

Otherwise, normal launches reuse the saved data. Errors in dump files are recorded in **`mii_client_check_cache/dump_index_errors.csv`**. Top1000 filename problems and ambiguities are recorded in **`top1000_mii_issues.csv`** and the most recent profile lookup’s **`top1000_lookup_issues.csv`**, also inside that cache folder. Fix or replace the listed files, then run the refresh command.

## Optional: show known player names

Without a player list, the program can find profiles but may label their owners **Unknown player**.

1. Open [All known CTGP identities](https://docs.google.com/spreadsheets/d/1WBPNQv7L8SbHmjAlSatqp0_ZpycNWDlf8OwyfaaG3Tk).
2. Select the tab containing the player table.
3. Use **File → Download → Comma-separated values (.csv)**.
4. Save it in your program folder as **`players.csv`**.
5. Start the program with:

```powershell
python mii_client_check.py --identities players.csv
```

The CSV needs the original `ctgp_player_ids` column. Names come from its `name`/`displayname` columns. If a row only has an MKWLeaderboards ID, the program shows that number instead of fetching a name online.

Profiles already grouped with your input in this player list are omitted from its CTGP match results, since they are already known links.

## Top1000 results and friend codes

With the main setup complete, all four search options can display matching Top1000 profiles. Top1000 matching uses the client IDs read from the Mii binaries; it does not assume that identical names belong to the same person. Filename matching stays case-sensitive and also checks numbered duplicates such as `JJ_14.mii` when the mapping lists `JJ`. Keep the downloaded Mii filenames unchanged. If several files fit the same JSON name, they are shown as **filename candidates**, not confirmed Miis belonging to that profile. Numbered candidates must also contain the expected embedded Mii name. An exact file does not hide its numbered siblings. Missing or invalid files are skipped and reported instead of ending the lookup; if nothing can be read, the program returns to the menu.

Friend codes are calculated from **Top1000 online PIDs only**. A Ghost Database profile number is instead the decimal client ID. These ID types must not be interchanged. When you search a Top1000 profile, that same profile is omitted from its own Top1000 match results.

## If something goes wrong

| What you see | What to check |
| --- | --- |
| Python cannot be found | Try `py` instead of `python`. If neither works, install Python and reopen PowerShell. |
| `can't open file ... mii_client_check.py` | Open PowerShell from the folder containing the extracted script, not from inside the ZIP or a different folder. |
| `No comparison dumps/cache found` | Check the folder names and extraction in step 3. |
| `No .json files` or `No .rkg files` | The selected folder needs to contain the extracted data files, not just the downloaded archive. |
| A JSON name such as `JJ` has only `JJ_1.mii`, `JJ_2.mii`, etc. | Numbered duplicates are supported. The program reads the candidates and labels ambiguous profile associations; no manual renaming is required. |
| Missing Top1000 JSON/Mii folder | Check that `ninrankings_pids.json` is beside the script and that `miis` contains the extracted Top1000 `.mii` files. Both are required for the main feature. |
| Invalid CRC, missing Mii data or bad JSON | The file is damaged, incomplete or not in the expected format. Check the error report and obtain a valid copy. |
| Chadsoft request fails or is incomplete | Use a profile present in the local CTGP dump, or try again later. |

## Advanced: keep the data on another drive

You do not have to move a large dump just to use the default folder names. Point to the real folders instead:

```powershell
python mii_client_check.py --ctgp-dir "E:\ctgp_profiles" --ninrankings-dir "E:\ninrankings"
```

Add other paths only when needed:

| Option | Points to |
| --- | --- |
| `--identities "D:\players.csv"` | The known-player CSV. |
| `--mii-dir "E:\miis"` | The required Top1000 Mii files, if stored elsewhere. |
| `--nin-pids-json "D:\ninrankings_pids.json"` | The required Top1000 filename mapping, if stored elsewhere. |
| `--cache "D:\mii_client_check_cache"` | Where the program saves its prepared data and downloaded headers. Keep using the same location. |

Use your actual drive letters and paths. Keep quotation marks around paths containing spaces. Include the same path options when running `--refresh-index`.

`--index-only` prepares/checks data and exits without opening the menu. `--index` accepts an existing compatible MiiConnect24 comparison database, but is unnecessary for a new setup. Run `python mii_client_check.py --help` for all options.

On macOS/Linux, use a terminal in the program folder and usually `python3` in place of `python`. The filenames and lookup steps are the same.

## Other public resources and credits

These are useful for investigation, but are **not required for the basic setup** above.

- [MiiConnect24 website](https://miiconnect24.pages.dev/) — browse matching reports in your browser.
- [Mysterious CTGP profiles](https://docs.google.com/spreadsheets/d/1HM32s2pliJOIAqHB_jcrE6jjeFLlfpXl_tEps6-30hc) — unresolved identities and investigation notes.
- [Players’ Page–MKWLeaderboards–MKWRS–CTGP links](https://docs.google.com/spreadsheets/d/1WIM9Qx6B06XNWZiE528vIFtmfFB9jMK5G8QjYthM9sk/edit?usp=sharing) — **not maintained after 23 October 2026**.
- [Players’ Page–NinRankings Top1000 links](https://docs.google.com/spreadsheets/d/1-vOFFf-SnqikbMtcYC80z-iIUhwlHJYGYZSEh-1zHm4/edit?gid=0#gid=0) — by **FalB and InnovΔ**. This reference sheet is not the Top1000 filename JSON used by Portable.
- [NinRankings Miis grouped by profile](https://mega.nz/file/SVgg2YRL#pATkmepKDmEZlnFyHeBQD8yS8Ya55yBIUTbSeEgtm-Q).
- [NinRankings Miis grouped by client ID](https://mega.nz/file/vRRkCD5T#fgIBxViZiNhtXdd4QqhKTtW-uhOsOV2ukqwa6tAM_jw).
- [Mii Renderer by PF2M & Arian](https://pf2m.com/tools/mii/) — view Mii faces separately. Portable itself prints text and links; it does not render images.
- [Useful sites for finding old times](https://pastebin.com/4MUi5Qun).
- [Tool to fetch a player’s last-used Mii on Wiimmfi](https://www.mediafire.com/file/is3t16r05z2wv4l/atfm_gui.zip/file).
- [MKLeaderboards MKW profile dump — 7 August 2026](https://mega.nz/file/LMRVQBDA#JYMvBK2aY0qsedjM3NnddZzycJBFYHnYZDs0Im5I-Ms) — historical reference, not an input for Portable. MKLeaderboards and MKWLeaderboards are different sites.
