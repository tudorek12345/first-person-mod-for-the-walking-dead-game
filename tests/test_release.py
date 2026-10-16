"""Public packages must use portable paths and exclude original game content."""
from pathlib import Path
import sys
import unittest

from lupa import lua51

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build_release import generated_config, FORBIDDEN


class ReleaseTests(unittest.TestCase):
    def test_config_uses_current_users_writable_log_directory(self):
        lua = lua51.LuaRuntime()
        lua.execute('os.getenv=function() return "D:\\\\Users\\\\test user\\\\AppData\\\\Local" end')
        lua.execute(generated_config('test-build', 'WalkingDead104'))
        self.assertEqual(lua.globals().FP_Generated.log_dir,
                         'D:/Users/test user/AppData/Local/First-person-mode/logs')
        self.assertEqual(lua.globals().FP_Generated.episode, 'WalkingDead104')
        self.assertFalse(lua.globals().FP_Generated.native_test)

    def test_config_falls_back_without_environment_library(self):
        lua = lua51.LuaRuntime()
        lua.execute('os=nil')
        lua.execute(generated_config('test-build', 'default'))
        self.assertEqual(lua.globals().FP_Generated.log_dir, '.')
        self.assertEqual(lua.globals().FP_Generated.log_path, './runtime.log')

    def test_payload_source_has_no_original_game_aliases(self):
        self.assertFalse(FORBIDDEN & {p.name for p in (ROOT / 'src').glob('*.lua')})
        config = generated_config('test-build', 'default')
        self.assertNotIn(str(ROOT), config)


if __name__ == '__main__':
    unittest.main()
