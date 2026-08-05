# Mario Kart DS Setup Guide

## Important

As we are using BizHawk, this guide is only applicable to Windows and Linux systems.

This world does **not** patch your ROM. There is no "Open Patch" step - you connect
directly to your own, already-legitimate copy of the game while it runs in BizHawk, and
the client reads/writes the emulator's live memory instead.

## Required Software

- BizHawk: [BizHawk Releases from TASVideos](https://tasvideos.org/BizHawk/ReleaseHistory)
  - Detailed installation instructions for BizHawk can be found at the above link.
  - Windows users must run the prereq installer first, which can also be found at the above link.
- The built-in Archipelago client, which can be installed [here](https://github.com/ArchipelagoMW/Archipelago/releases)
- A Mario Kart DS (EU, En/Fr/De/Es/It) ROM file, game code AMCP. The Archipelago
  community cannot provide this. Other regions (e.g. USA/AMCE) are not currently
  supported - the client validates the exact game code and will refuse to connect to
  anything else.

## Configuring BizHawk

Once BizHawk has been installed, open EmuHawk and change the following settings:

- Under Config > Customize, check the "Run in background" box. This will prevent
  disconnecting from the client while EmuHawk is running in the background.
- Under Config > Customize > Advanced, make sure the box for AutoSaveRAM is checked, and
  click the 5s button. This reduces the possibility of losing save data in emulator
  crashes.

It is strongly recommended to associate Nintendo DS ROM extensions (\*.nds) with EmuHawk.
To do so, right click any DS ROM you own, select "Open with...", "Look for another
application", then browse to the BizHawk folder and select EmuHawk.exe.

## Configuring your YAML file

### What is a YAML file and why do I need one?

Your YAML file contains a set of configuration options which provide the generator with
information about how it should generate your game. Each player of a multiworld
provides their own YAML file. This setup allows each player to enjoy an experience
customized for their own taste, and different players in the same multiworld can all
have different options.

### Where do I get a YAML file?

You can generate a YAML file by visiting the Mario Kart DS Player Options page on the
Archipelago website (once this world is hosted there), or write one by hand using the
option names/values in this world's `options.py` as a reference.

## Joining a MultiWorld Game

Unlike most Archipelago games, there's no ROM to generate or patch for Mario Kart DS -
you already have everything you need once you have a legitimate copy of the game.

1. Start EmuHawk and load your Mario Kart DS ROM directly (File > Open ROM). Do not use
   "Open Patch" from the Archipelago launcher for this game - there is no patch file to
   open.
2. In EmuHawk, go to `Tools > Lua Console`. This window must stay open while playing.
3. In the Lua Console window, go to `Script > Open Script…`.
4. Navigate to your Archipelago install folder and open
   `data/lua/connector_bizhawk_generic.lua`.
5. The emulator may freeze every few seconds until it manages to connect to the client.
   This is expected.
6. Open `ArchipelagoLauncher.exe` and select "BizHawk Client" from the list. The client
   window should indicate that it connected to BizHawk and recognized Mario Kart DS.
7. To connect the client to the multiserver, type `<address>:<port>` (e.g.
   `archipelago.gg:38281`) into the top text field of the client and press enter (if the
   server uses a password, type `/connect <address>:<port> [password]` in the bottom
   text field instead).

You must keep the BizHawk Client connected to both BizHawk and the multiserver for
checks to send and items to arrive, even in a single-player game.

## Playing the game

Play Mario Kart DS as normal - **every character, kart, and cup is selectable from the
start** (the client forces this the moment it connects, regardless of your starting
save). This is intentional, not a bug: see "How enforcement works" below. Only
cups/races/time trials/missions that are actually needed for your selected goal send
checks - everything else behaves exactly like the unmodified game.

Your *starting* legitimate loadout - what will actually earn a check if you use it right
away - is one random character, one random kart (any of the 36 real karts - not tied to
the character, matching the base game), and (for whichever of Cups/Time Trial/Missions
your YAML turns on) one starting cup, one starting Time Trial track, and one starting
mission. Everything else in a given section needs its own item from the multiworld
before races using it will earn checks - see "How enforcement works" for what happens if
you use something you haven't earned yet.

### How enforcement works

Mario Kart DS has no internal flag governing its baseline content (the 8 starter
characters, their default karts, and 4 of the 8 cups are always available in vanilla,
with nothing for this world to restrict), and no way to patch that at the binary level
has been found despite extensive investigation (see `NOTES_ARCHIVE.md` in the source
repository). Rather than leave that content unenforced, this world takes a different
approach: **everything is selectable, but a check only sends if the character and kart
you actually raced with were legitimately received from the multiworld first.** If
Randomize Karts is on, that applies per-kart, the same way it applies per-character: one
random kart is free for the whole seed, and every other one of the 36 real karts needs
its own item before races using it will earn a check - whichever kart you're actually
driving when you win is the one that has to be legitimate, not a fixed universal item.

In practice: nothing stops you from racing with an unearned character or kart, but doing
so simply won't earn a check. There's no error or warning - the check just silently
doesn't fire. This is the same trust-based model many Archipelago games use for content
that can't be hard-restricted at the game level.

### Current status

Grand Prix (individual race wins and overall cup wins), Mission Mode clears, and goal
completion are fully implemented and live-verified against real gameplay, including the
underlying character/kart identity reads (which character_id/kart_id RaceConfig reports
for the player's own race). Time Trial's finish-time decode (comparing your time against
a reference time, rather than reading real ghost data) is also confirmed live.
**Not yet live-verified** (implemented, but pending confirmation against real BizHawk
gameplay): all 36 karts individually unlocking (as opposed to the single "Standard Kart"
item this replaced, which WAS live-verified) - the kart_id-to-name mapping and the
free-kart-by-name check are new and haven't been exercised against a real race yet, even
though the underlying read they're built on has been. Also still open: the character/kart
identity reads specifically for cup-win and mission-clear checks (as opposed to race
wins), and Time Trial's own end-of-run detection heuristic specifically (Time Trial has
no CPU racers, so it can't reuse the same "real race finish" signal Grand Prix does) -
the rest of the Time Trial check (finish-time comparison itself) is solid.

See this world's `rom_addresses.py`/`NOTES.md` in the source repository for full technical
detail.
