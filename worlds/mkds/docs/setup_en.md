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

Play Mario Kart DS as normal from a fresh save. Characters, Cups, and/or Karts (depending
on your YAML options) start locked and unlock as the corresponding items arrive from the
multiworld. Only cups/races/time trials/missions that are actually needed for your
selected goal send checks - everything else behaves exactly like the unmodified game.

**Current status**: this world is still under active development. Grand Prix (individual
race wins and overall cup wins, goal completion) and Mission Mode clears are fully
implemented and live-verified against real gameplay. Not yet working: Kart items are
received but not applied in-game (no starting-kart randomization yet), Time Trial has
locations defined but no in-game detection for actually beating a staff ghost, and Mission
Mode's "3 Stars" rank isn't detected (only "Clear" is) - a seed whose goal depends on Time
Trial or mission rank cannot currently be completed. Cup-based goals (the default) work
end-to-end today.

**Known limitation - vanilla baseline content is not suppressed.** Item checks/receives,
required-location gating, and the goal itself all work correctly for the 9 things the game
tracks with its own internal unlock flags (4 non-default cups, Mirror Mode, Dry Bones,
Daisy, Waluigi, R.O.B.). However, Mario Kart DS treats its **8 starter characters, each
character's first 2 karts, and 4 of the 8 cups as always available**, with no internal flag
governing that access at all - there is nothing for this world to write to restrict it. In
practice this means: from a fresh save, you can select any of the 8 starter characters,
their starting karts, and play the 4 default-unlocked cups immediately, regardless of
whether you've received the corresponding Archipelago items yet. This is a trust-based
limitation, not a logic bug - the multiworld's item/location model is still fully correct
(a seed cannot be completed without the right items in-logic), it's just not
*enforced in-game* for this specific baseline content the way it is for everything else.
Suppressing it would require a binary ASM patch to the ROM itself (rather than the RAM
writes this world currently uses), which has been investigated at length but not yet
achieved - see `NOTES.md` in the source repository for the full investigation if you want
to pick it up.

See this world's `rom_addresses.py`/`NOTES.md` in the source repository for full technical
detail.
