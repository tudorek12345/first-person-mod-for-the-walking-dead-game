-- Retain ownership of failed restoration work until it succeeds. This queue
-- never drops a failed task or lets one teardown failure stop another task.
FP_Cleanup={}
local C=FP_Cleanup
local delays={0.25,1,3}
function C.new(logger)
  local self={tasks={},serial=0,clock=0}
  local function report(event,task,extra)
    local fields={cleanup_id=task.id,label=task.label,attempt=task.attempts}
    for k,v in pairs(extra or {}) do fields[k]=v end
    if logger and logger.write then
      pcall(logger.write,event=="cleanup_blocked" and "warn" or "info",event,fields)
    end
  end
  local function call(task)
    task.attempts=task.attempts+1
    if logger and logger.try then
      -- A logging failure must not interrupt unrelated compensation tasks.
      local outer,ok,value=pcall(logger.try,task.label,task.fn)
      if outer then return ok,value end
      return false,ok
    end
    return pcall(task.fn)
  end
  local function failed(task)
    local delay=delays[task.attempts]
    task.blocked=delay==nil
    task.due=self.clock+(delay or 0)
    if task.blocked then report("cleanup_blocked",task)
    else report("cleanup_queued",task,{delay=delay}) end
  end
  function self:run(label,fn)
    assert(type(fn)=="function","Cleanup task must be a function")
    self.serial=self.serial+1
    local task={id=self.serial,label=tostring(label),fn=fn,attempts=0,blocked=false}
    local ok,value=call(task)
    if ok then return true,value end
    failed(task)
    self.tasks[#self.tasks+1]=task
    return false,value
  end
  function self:tick(dt)
    if type(dt)~="number" or dt~=dt or dt==math.huge or dt==-math.huge then dt=0 end
    self.clock=self.clock+math.max(0,dt)
    -- Snapshot the count: a task may enqueue another compensation task.
    local count=#self.tasks
    for index=1,count do
      local task=self.tasks[index]
      if not task.blocked and self.clock>=task.due then
        report("cleanup_retry",task)
        local ok=call(task)
        if ok then task.done=true; report("cleanup_completed",task)
        else failed(task) end
      end
    end
    local remaining={}
    for _,task in ipairs(self.tasks) do
      if not task.done then remaining[#remaining+1]=task end
    end
    self.tasks=remaining
  end
  function self:reset()
    for _,task in ipairs(self.tasks) do
      if task.blocked then
        task.blocked,task.attempts,task.due=false,0,self.clock
        report("cleanup_rearmed",task)
      end
    end
  end
  function self:pending() return #self.tasks end
  function self:blocked()
    local count=0
    for _,task in ipairs(self.tasks) do if task.blocked then count=count+1 end end
    return count
  end
  return self
end
