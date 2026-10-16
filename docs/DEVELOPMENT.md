# Development and diagnostics

Developer reference for the original Windows Steam Season One, episodes 1–5. This does not cover later seasons or Definitive Series. Full campaign progression remains unverified. See the [README](../README.md) for the release installer.

## Controls

| Control | Action |
| --- | --- |
| F6 | Toggle first person and restore the original camera |
| F8 | Rebuild mod components and retry recovery; keeps F6-off disabled |
| Mouse | Look during exploration and noninteractive cutscenes; native aim in scripted combat |
| Hold right mouse | Aim with a drawn gun; look around during station views and supported interactive scenes |
| Hold Tab | Return cutscene view toward its focus target; reset station look offset |
| WASD | Original walking or cover/peek actions, with original walkboxes |
| G | Draw/holster the exploration weapon |
| 1 / 2 / 3 | Pistol / shotgun / rifle while drawn |
| Left mouse | Fire a drawn exploration weapon |
| R | Reload |
| F | Use the focused original interaction during exploration |
| Hold Alt | Restore the authored camera framing and release the cursor for original interactions |

Dialogue, QTEs, cover actions and scripted combat retain their original input handlers. Free-fire is limited to exploration. Story characters are immune by default. Configuration is in `src/fp_config.lua`; rebuild after editing it.

First-person FOV is 100 degrees, narrowing to 65 while aiming. Standing views use a 14 cm offset above the head bone (10.5 cm higher than the previous build). The offset blends down to 3.5 cm for crouched/seated poses and short avatars, using head height relative to the avatar root; stairs do not change that measurement. Authored interaction cameras retain their original height and FOV. This is a bounded height adjustment, not an obstruction or ceiling collision solver. Position logs include head height, applied eye offset, eye source and actual FOV.

The shared policy now covers native shotgun/sniper aiming, balance/struggle QTEs, spatial action/directional choices, telescope/object close-ups, stations, cover and recaps. Scripted combat keeps its absolute cursor and authored projection; the mod does not recenter its aiming cursor. Close-ups retain original panning and interaction callbacks. Recaps preserve their authored position and permit cutscene free-look. These policies are installed in every episode patch, not selected by individual level names.

Station and cover sequences use the original camera position, orientation and FOV while interacting. Hold right mouse to look around; release it to return to the interaction view. This deliberately preserves their authored viewpoint, which can be far from the player model. It avoids the motel barrier bug where the interaction camera was pulled roughly 32 metres back to crouching Lee.

Cutscene focus prefers an explicit game look target, then an actor near the original shot axis, then the authored camera direction. Moving the mouse overrides automatic centering. After 2.5 seconds without mouse movement, the view gently recenters; Tab recenters faster. Actor selection from shot framing is a heuristic, so it cannot guarantee every narrative detail is chosen correctly. Choice and QTE cursors remain available; full mouse capture starts only when both native cutscene movement and interaction modes are active.

Disabled native look-at targets are ignored. A small selection margin and heading smoothing reduce rapid switching between nearby actors. Hidden avatars use the authored viewpoint. Cameras attached to moving rigs retain their authored local position/rotation, so movement of the parent cannot corrupt camera restoration.

The 0.5.1 controller retains user look and focus heading across camera cuts while following the same avatar. A 120 ms focus-selection delay filters single-frame native shots. Head translation is smoothed relative to the avatar root with at most 12 cm of lag; ordinary walking and mouse rotation remain immediate. Position spikes are held for roughly 80 ms of consistent destination samples and rejected if they disappear. Changing destinations or invalid samples reset confirmation. Confirmed actor relocations remain first person with the same FOV and look offsets, without a detour to the authored camera. The controller never moves story actors or interpolates the camera through metres of unknown geometry. It cannot remove intentional choreography cuts without rewriting those scenes. Continuously unstable samples keep the last validated view until usable data returns; hold duration is logged. Invalid head positions fall back to the authored view and log onset/recovery rather than repeating a warning every frame.

An earlier recovery policy inserted a 350 ms trip to the authored camera after confirmed actor relocations, creating extra visible cuts. That automatic actor-relocation fallback has been removed. Every policy transition now logs its reason (including manual Alt), before/after camera positions and displacement, so short excursions cannot disappear between the two-second samples.

The original `module_visibility.lua` hides characters and objects by camera name, even after that camera has moved into first person. Each episode patch now preserves its original compiled module under an alias and wraps only that module's camera callback. First person compensates its hide-only rules; returning to an authored view restores them. Ordinary `AgentHide` calls, choreography visibility proxies and exclusive show-only variants retain control. Camera-only hiding of the player's body no longer forces the camera out of first person. Failed visibility restoration retains its records and retries independently. This does not force every hidden story object to appear, smooth NPC choreography, or disable renderer culling.

## Automatic recovery

Transient mod frame errors restore the original camera, head visibility and cursor, then rebuild the adapter after 0.25, 1 and 3 seconds. Four failures within 60 seconds stop automatic retries for that scene. F8 or a scene change resets the retry limit. F6-off is never reversed by recovery. Ammo is preserved, and recovery does not teleport the player or change quest flags.

Weapons, firing, HUD and focus have separate retry limits so an optional component failure does not disable the camera. Repeated weapon failures holster the gun, restoring native clicks. Missing cameras release mouse capture until a camera returns. A scene watchdog can recover a missed open callback when a different valid scene/avatar becomes active. All recovery attempts, fallback states and successful restarts are logged. This is bounded state recovery, not a system that invents and installs code fixes at runtime.

Failed cleanup retains each outstanding camera, property and object operation and retries it independently, even with F6 disabled. Permanent failures retain their restoration records for F8 or a new scene. The adapter restores all active ownership before waiting on unfinished cleanup, preventing a frozen first-person view with native controls. Input guards inspect current engine modes, so the first choice click or pause update is not swallowed by stale exploration state. Unrelated UI scene-open notifications cannot reopen a closing gameplay scene.

## Logs and diagnostics

Release installs write runtime logs under `%LOCALAPPDATA%\First-person-mode\logs`. Developer builds write `build/logs/fp-*.jsonl`. Each game Lua session gets a separate file. A process can create several sessions when changing episodes or loading scenes. Records include the source build fingerprint, native-test flag, episode, scene, actor, active camera, mode, focus source/target, recovery state, weapon events, frame count, errors and available stack information. Camera/player/authored positions, station state, cursor capture and WASD state are sampled every two seconds while attached. Heartbeats are written every ten seconds. Logs close after each record, rotate at 2 MiB, and rate-limit repeated identical errors while recording occurrence counts.

For developer builds, `build/runtime.log` is the readable aggregate. The generated configuration controls the destination; release installer logs, backups, work files and cache use `%LOCALAPPDATA%\First-person-mode`. Generate a report for the last built version:

```powershell
python tools/check_logs.py
```

The result is `build/diagnostics.json`, including recovery records and Windows Application Error, crash-report and hang events mentioning `WalkingDead101.exe`. Use `--all-builds` for earlier experiments, `--build <fingerprint>` for one build, or `--since 2026-10-15T23:40:00Z` for a time filter. `--no-windows` performs only offline log analysis. A missing clean-exit record alone is not classified as a crash: the engine also resets Lua sessions when changing scenes.

Diagnostics now flag prolonged player waits, camera identity/projection mismatches, unusual actor-camera separation and repeated movement input without displacement. These are evidence-linked symptoms requiring review, not automatic proof of a progression bug; walls and scripted scenes can legitimately prevent movement. Incomplete live JSONL appends are distinguished from corrupt records. Runtime capability records show which gun prefab candidates are available in each attached scene.

The motion monitor records held/rejected/confirmed jumps per frame, plus fallback entry/exit. Camera samples include target versus rendered eye position, hidden-avatar ownership and near/far clipping and culling properties. Visibility snapshots record nearby actors and camera-managed objects, their hidden/runtime/proxy state, overrides and restoration. Reports distinguish sparse sampled movement from frame-confirmed discontinuities and flag single-frame camera activations.

The same command refreshes `build/scene-coverage.json`: an inventory of 86 story-scene resources found in the indexed archives across episodes 1–5. It lists unobserved scenes, observed modes/cameras, errors and warnings. Native fixture actors and older builds do not count toward current gameplay coverage; real gameplay after fixtures finish does count. Observation never marks a scene as a verified playthrough. Archives whose indexes could not be read are listed separately. Run `python tools/scene_coverage.py` to refresh only this report.

Logging covers the mod's protected Lua boundaries and available Windows crash events. It cannot guarantee a useful stack for native crashes, engine-suppressed failures, power loss, or third-party DLL faults. Retail `debug.traceback` can return an empty string; the logger preserves the error and falls back to `debug.getinfo`.

## Build, test and uninstall

Source builds require separately obtained third-party tools; downloaded binaries are excluded from this repository. Place compatible `luac.exe` under `tools/telltale-lua/` and `ttarchext.exe` under `tools/ttarchext/`. The game uses custom Lua 5.1 bytecode with 32-bit numbers, so a stock Lua compiler is not interchangeable. Python 3.12 was used. Tests require `python -m pip install -r requirements-dev.txt`.

Extract resources from your own installed game before building: `python tools/extract_scripts.py --game "D:\SteamLibrary\steamapps\common\The Walking Dead"`. Replace that example path with your installation. The builder accepts the same `--game` argument. Optional decompilation requires `tools/telltale-lua/unluac.jar` and a Java 21 runtime under `tools/java/jdk-21*/bin/java.exe`. Tool sources are linked in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

```powershell
python -m unittest discover -s tests -v
python tools/build_mod.py --install
```

Close the game before installation; the installer refuses to modify a running installation. It compiles the scripts, produces sorted classic TTARCH patches, extracts each result and compares every script byte-for-byte. Only `Pack/<episode>/0_00_firstperson.ttarch` is installed. Replaced versions of this mod are backed up under `build/install-backups/`. Original game archives, translations, graphics DLLs and saves are not replaced by the installer.

For native tests using disposable agents at startup:

```powershell
python tools/build_mod.py --native-test --install
```

Launch the game through Steam and wait at the title screen. Tests query the real head bone, apply the camera/head adapter, create and position all three weapon prefabs, verify station projection restoration, focus direction and screen projection, check error details, and verify deferred agent destruction. They skip when gameplay is already active. Reinstall **without** `--native-test` for ordinary play.

To remove the mod while retaining a backup of its patches:

```powershell
python tools/build_mod.py --uninstall
```

## Current coverage and remaining work

The automated tests exercise ammo/reloading, input transitions, cursor release, camera restoration, scene identity, visibility, camera changes, station projection, cutscene focus, native cursor recentering, fault recovery, logging, coverage accounting and packaging. Native tests exercise actual engine APIs; they do not reproduce the whole motel stealth sequence or a full episode.

Validation on 2026-10-16: **224 local tests passed; 14 native checks passed**, including actual original visibility-module interception and hide restoration, moving-parent camera restoration, 100-degree FOV readback and Lee's raised standing eye height (about 1.79 m on the native fixture). Local regressions also cover camera-cut continuity, head smoothing, transient-jump rejection, invalid-head fallback, story/camera visibility ownership, optional native arguments, fault isolation, crouched/short avatars and focus alignment. The final native run logged no Lua errors, warnings or Windows crash events. Evidence is in `build/local-test-results.txt` and `build/native-test-results.json`; the latter records its exact source fingerprint. The normal installed patches have native fixtures disabled.

The previous build's new logs exposed 71 seconds / 4,828 frames of missing-player waits after the Episode 4 recap: the bottom scene was `adv_savannahstreets`, but the actor's scene resource used `.scene`. Scene matching now canonicalizes paths, case and extensions. A subsequent native session attached Lee in Savannah River Street within a few frames and logged no Lua errors; this is runtime attachment evidence, not a completed chapter.

The station adapter uses the original `Station_GetCurrent()` and `cam_station.prop` camera ancestry, rather than a level-name exception. It applies across all five episode patches. `mode_peek` retains native directional actions. Exploration removes fixed navigation-axis overrides so original walkbox movement follows the first-person camera. The motel barrier station still needs a complete gameplay retest with the current build.

Unrestricted free walking through story-locked scenes is not implemented. Walking uses the game's walkboxes and scripted navigation, including station/cover transitions. Forcing arbitrary movement there would also require replacing the associated choreography, triggers and progression logic.

The free-fire weapons use existing models and sounds with procedural positioning, recoil, muzzle effects and reload motion. They do not yet have a bespoke first-person arm rig or authored hand/reload animations. Generic walker damage does not implement every scene's bespoke quest, death or combat logic. Shot occlusion, gun alignment, every dialogue/QTE and all episode transitions still need gameplay coverage. No claim of a perfect end-to-end conversion is made.

`python tools/audit_episode_assets.py` produces `build/episode-assets.json` with archive provenance for helper, head, weapon and sound candidates. Episode 5's indexed local archives lack the configured shotgun/rifle candidates; they exist in other episodes, but cross-episode mounting needs runtime verification. Audio availability is unverified because the audio archive indexes could not be read. Missing gun models now trigger bounded recovery and leave native clicks available rather than retrying every frame.

## Local reverse engineering

`tools/extract_scripts.py` and `tools/decompile_scripts.py` produced a local archive/script provenance manifest and decompiled reference scripts under `research/`. Of 454 unique extracted scripts, 452 decompiled; `mode_sniper.lua` and `ui_gameplay_common.lua` did not. Their original compiled resources remain unchanged. This is script extraction and targeted native API inspection, not a decompilation of the entire executable into original source.

`research/`, extracted game content, downloaded tools, build products and save backups are excluded by `.gitignore`. The original bootstrap and visibility module are obtained from the installed game and embedded only in locally generated patches, with per-episode hashes in the build manifest. Generated game-resource patches are not original MIT-licensed mod code and are excluded from the source repository.

Tools/references: [Luigi Auriemma's ttarchext](https://aluigi.altervista.org/papers.htm#ttarchext), [TTG-Tools](https://github.com/HeitorSpectre/TTG-Tools), and [Telltale Lua scripting documentation](https://github.com/frostbone25/TelltaleLuaScriptingDocumentation). The public [AgentHide signature](https://github.com/frostbone25/TelltaleLuaScriptingDocumentation/blob/main/LuaFunctions/AgentHide.md) includes an optional third argument; the wrapper preserves all arguments. The [Telltale Cutscene Editor](https://github.com/Telltale-Modding-Group/Telltale-Cutscene-Editor) targets Definitive Series, so it was consulted as context rather than installed in this original Season One game. Visibility behavior was traced through this installation's decompiled `module_visibility.lua`, `_system.lua` visibility proxy and Episode 2 scene scripts, then checked with native fixtures.


## Release installer and reporting

The release package uses `Install.cmd` and `Uninstall.cmd` with PowerShell; end users do not need Python. The installer detects Steam libraries and prompts for the game folder if detection fails. It obtains the required archive tool separately and builds patches from the installed game. Runtime logs, installer logs, cached tools and backups are stored under `%LOCALAPPDATA%\First-person-mode`.

The recorded controller/native validation above is not a claim that the release installer has been tested on every PC. Report version, episode, location, triggering action and a relevant log excerpt. Review logs before posting publicly: generated paths can contain local account or directory names.
