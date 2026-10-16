-- Preserve the game's bootstrap and record errors before adapter setup.
require("fp_generated.lua")
require("fp_log.lua")
FP_Log.write("info","bootstrap_enter")
local originalOK,originalError=FP_Log.try("original_bootstrap_error",require,"fp_original_system.lua")
if not originalOK then assert(false,originalError) end
FP_Log.write("info","original_bootstrap_finished")
FP_Log.try("adapter_bootstrap_error",require,"fp_main.lua")
