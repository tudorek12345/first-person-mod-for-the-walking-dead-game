"""Run the Windows PowerShell installer helpers against disposable game folders."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from ttarch_patch import pack

POWERSHELL=shutil.which('powershell.exe')
EPISODES=['default','WalkingDead102','WalkingDead103','WalkingDead104','WalkingDead105']
HEADER=bytes.fromhex('1b4c75615100010404040400')


def ps_quote(value):
    return "'"+str(value).replace("'","''")+"'"


@unittest.skipUnless(POWERSHELL,'Windows PowerShell is required')
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='fp installer tests ')
        self.addCleanup(self.temporary.cleanup)
        self.work=Path(self.temporary.name)
        self.game=self.work/'game folder'
        self.game.mkdir()
        (self.game/'WalkingDead101.exe').write_bytes(b'fixture, never executed')
        for episode in EPISODES:
            (self.game/'Pack'/episode).mkdir(parents=True)

    def run_ps(self,body):
        script=self.work/'case.ps1'
        script.write_text("$ErrorActionPreference='Stop'\n. "+ps_quote(ROOT/'installer/Installer.Core.ps1')+'\n'+body,encoding='utf-8')
        result=subprocess.run([POWERSHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        return result.stdout

    def payload(self):
        payload=self.work/'payload'
        manifest={'format':1,'build':'testfixture','episodes':[]}
        for episode in EPISODES:
            folder=payload/episode
            folder.mkdir(parents=True)
            files=[]
            for name in ['_system.lua','module_visibility.lua','fp_main.lua','fp_generated.lua']:
                data=HEADER+b'local bytecode fixture'
                (folder/name).write_bytes(data)
                files.append({'name':name,'sha256':hashlib.sha256(data).hexdigest()})
            manifest['episodes'].append({'episode':episode,'scripts':files})
        (payload/'manifest.json').write_text(json.dumps(manifest))
        return payload,manifest

    def patch_records(self):
        records=[]
        for episode in EPISODES:
            source=self.work/(episode+'.ttarch')
            source.write_bytes(('new mod patch '+episode).encode())
            records.append({'episode':episode,'archive':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
        path=self.work/'patches.json'
        path.write_text(json.dumps(records))
        return path,records

    def test_binary_archive_writer_matches_verified_python_layout(self):
        output=self.work/'written.ttarch'
        self.run_ps('Write-TtarchV3 @{"z.lenc"=[byte[]](0,1,255);"a.lenc"=[byte[]](9,8)} '+ps_quote(output))
        self.assertEqual(output.read_bytes(),pack({'z.lenc':b'\0\1\xff','a.lenc':b'\x09\x08'}))

    def test_boundary_guard_rejects_traversal_and_sibling_prefix(self):
        self.run_ps('''
          $root=ROOT
          $good=Assert-Within (Join-Path $root 'Pack\\default\\0_00_firstperson.ttarch') $root
          if (-not $good) { throw 'Valid path was rejected' }
          foreach ($bad in @((Join-Path $root '..\\escaped'),($root+'-sibling\\file'))) {
            $rejected=$false
            try { Assert-Within $bad $root | Out-Null } catch { $rejected=$true }
            if (-not $rejected) { throw 'Unsafe path was accepted' }
          }
        '''.replace('ROOT',ps_quote(self.game)))

    def test_prepare_only_entrypoint_rejects_game_output_before_payload_or_download(self):
        before={str(p.relative_to(self.game)):p.read_bytes() for p in self.game.rglob('*') if p.is_file()}
        environment=os.environ.copy()
        environment['LOCALAPPDATA']=str(self.work/'local app data')
        for output in (self.game,self.game/'nested prepared',self.game/'Pack'/'..'/'prepared'):
            with self.subTest(output=output):
                result=subprocess.run([POWERSHELL,'-NoProfile','-ExecutionPolicy','Bypass','-File',
                    str(ROOT/'installer/Install.ps1'),'-GamePath',str(self.game),
                    '-PayloadRoot',str(self.work/'intentionally missing payload'),
                    '-PrepareOnly','-OutputRoot',str(output),'-NoPrompt'],
                    capture_output=True,text=True,env=environment)
                self.assertEqual(result.returncode,1,result.stdout+'\n'+result.stderr)
                self.assertIn('OutputRoot must be outside the game folder',result.stdout)
                self.assertNotIn('Downloading',result.stdout)
                after={str(p.relative_to(self.game)):p.read_bytes() for p in self.game.rglob('*') if p.is_file()}
                self.assertEqual(after,before)
                if output!=self.game:
                    self.assertFalse(output.exists())

    def test_valid_payload_is_accepted_and_corruption_is_rejected(self):
        payload,_=self.payload()
        self.run_ps('''
          Read-PayloadManifest PAYLOAD | Out-Null
          [IO.File]::AppendAllText((Join-Path PAYLOAD 'default\\fp_main.lua'),'changed')
          $rejected=$false
          try { Read-PayloadManifest PAYLOAD | Out-Null } catch { $rejected=$true }
          if (-not $rejected) { throw 'Corrupted payload was accepted' }
        '''.replace('PAYLOAD',ps_quote(payload)))

    def test_original_game_script_alias_is_rejected_from_distributable_payload(self):
        payload,manifest=self.payload()
        entry=manifest['episodes'][0]['scripts'][0]
        entry['name']='fp_original_system.lua'
        (payload/'default'/entry['name']).write_bytes((payload/'default'/'_system.lua').read_bytes())
        (payload/'manifest.json').write_text(json.dumps(manifest))
        self.run_ps('''
          $rejected=$false
          try { Read-PayloadManifest PAYLOAD | Out-Null } catch { $rejected=$true }
          if (-not $rejected) { throw 'Commercial script alias was accepted in release payload' }
        '''.replace('PAYLOAD',ps_quote(payload)))

    def test_five_episode_install_and_uninstall_preserve_other_files_and_backups(self):
        record_path,records=self.patch_records()
        for episode in EPISODES:
            (self.game/'Pack'/episode/'0_00_firstperson.ttarch').write_bytes(b'previous mod')
            (self.game/'Pack'/episode/'another-mod.ttarch').write_bytes(b'unrelated mod')
        data=self.work/'local data'
        self.run_ps('''
          function Assert-GameClosed {}
          $game=Resolve-GamePath GAME -NoPrompt
          $records=[IO.File]::ReadAllText(RECORDS) | ConvertFrom-Json
          $backup=Install-PreparedPatches $game $records DATA
          foreach ($record in $records) {
            if ((Get-Sha256 (Join-Path (Join-Path (Join-Path $game 'Pack') $record.episode) '0_00_firstperson.ttarch')) -ne $record.sha256) { throw 'Wrong installed hash' }
            if ([IO.File]::ReadAllText((Join-Path (Join-Path $backup $record.episode) '0_00_firstperson.ttarch')) -ne 'previous mod') { throw 'Missing old patch backup' }
          }
          Uninstall-Mod $game DATA
        '''.replace('GAME',ps_quote(self.game)).replace('RECORDS',ps_quote(record_path)).replace('DATA',ps_quote(data)))
        for episode in EPISODES:
            self.assertFalse((self.game/'Pack'/episode/'0_00_firstperson.ttarch').exists())
            self.assertEqual((self.game/'Pack'/episode/'another-mod.ttarch').read_bytes(),b'unrelated mod')
        self.assertEqual(len(list((data/'uninstalled').rglob('0_00_firstperson.ttarch'))),len(records))

    def test_mid_install_verification_failure_rolls_back_previous_episodes(self):
        record_path,records=self.patch_records()
        old=self.game/'Pack'/'default'/'0_00_firstperson.ttarch'
        old.write_bytes(b'previous first episode')
        records[1]['sha256']='0'*64
        record_path.write_text(json.dumps(records))
        self.run_ps('''
          function Assert-GameClosed {}
          $records=[IO.File]::ReadAllText(RECORDS) | ConvertFrom-Json
          $failed=$false
          try { Install-PreparedPatches GAME $records DATA | Out-Null } catch { $failed=$true }
          if (-not $failed) { throw 'Fault injection did not stop installation' }
        '''.replace('GAME',ps_quote(self.game)).replace('RECORDS',ps_quote(record_path)).replace('DATA',ps_quote(self.work/'local data')))
        self.assertEqual(old.read_bytes(),b'previous first episode')
        self.assertFalse((self.game/'Pack'/'WalkingDead102'/'0_00_firstperson.ttarch').exists())
        self.assertFalse(list(self.game.rglob('*.tmp')))
        self.assertEqual(len(list((self.work/'local data'/'backups').rglob('0_00_firstperson.ttarch'))),1)

    def test_running_game_is_rejected_without_process_termination(self):
        self.run_ps('''
          function Get-Process { return [pscustomobject]@{Id=123;Name='WalkingDead101'} }
          $rejected=$false
          try { Assert-GameClosed } catch { $rejected=$true }
          if (-not $rejected) { throw 'Running game was accepted' }
        ''')

    def test_native_argument_quoting_preserves_spaces_backslashes_and_literal_dollars(self):
        capture=self.work/'capture arguments.ps1'
        capture.write_text('[Console]::Write(($args | ConvertTo-Json -Compress))',encoding='utf-8')
        output=self.run_ps('''
          $result=Invoke-Archiver TOOL @('-NoProfile','-ExecutionPolicy','Bypass','-File',CAPTURE,'C:\\folder with spaces\\','literal$dollar','embedded"quote') WORK
          Write-Output $result
        '''.replace('TOOL',ps_quote(POWERSHELL)).replace('CAPTURE',ps_quote(capture)).replace('WORK',ps_quote(self.work)))
        self.assertEqual(json.loads(output),['C:\\folder with spaces\\','literal$dollar','embedded"quote'])


if __name__=='__main__': unittest.main(verbosity=2)
