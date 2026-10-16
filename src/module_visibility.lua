-- Local original bytecode is copied to this alias by the build tool.
-- Scope only this original module's camera callbacks; preserve its behavior.
require("fp_visibility.lua")
FP_Visibility.load_original(function() return require("fp_original_visibility.lua") end)
