-- Pure camera/input policy shared by the retail adapter and regression tests.
FP_Policy={}
local P=FP_Policy

function P.scene_name(value)
  if value==nil then return "none" end
  local name=string.lower(string.gsub(tostring(value),"\\","/"))
  name=string.match(name,"([^/]+)/?$") or ""
  if name=="" or name=="none" then return "none" end
  if not string.find(name,"%.scene$") then name=name..".scene" end
  return name
end

function P.presentation(value)
  local name=P.scene_name(value)
  -- These resource families are present in the installed Season One archives.
  -- Do not classify ordinary story scenes using a broad substring like 'on'.
  return string.match(name,"^adv_previouslyon%d+%.scene$")~=nil
    or string.match(name,"^adv_nexttimeon%d+%.scene$")~=nil
    or name=="ui_closingcredits.scene" or name=="ui_credits.scene"
    or name=="ui_nexttime.scene"
end

function P.context(f)
  if not f.main then return "paused" end
  -- Spatial action choices need the authored shot; conversation text does not.
  if f.action_choice or f.direction_choice then return "choice" end
  if f.dialogue then return "dialogue" end
  if f.qte then return "qte" end
  if f.combat then return "combat" end
  if f.peek then return "peek" end
  if f.station then return "station" end
  if f.closeup then return "closeup" end
  if f.presentation then return "presentation" end
  if f.cinematic then return "cinematic" end
  if f.explore then return "explore" end
  return "scripted"
end

function P.authored(ctx)
  return ctx=="station" or ctx=="peek" or ctx=="closeup" or ctx=="combat"
    or ctx=="qte" or ctx=="choice" or ctx=="presentation"
end

function P.mouse_look(ctx,f)
  f=f or {}
  if f.alt then return false end
  -- These modes read absolute cursor coordinates or directional choice input.
  -- Recentring the OS cursor would silently change original game progression.
  if ctx=="combat" or ctx=="qte" or ctx=="choice" or ctx=="paused"
    or ctx=="inactive" then return false end
  if ctx=="explore" then return true end
  if (ctx=="cinematic" or ctx=="presentation") and f.full_cutscene then return true end
  return f.right==true
end
