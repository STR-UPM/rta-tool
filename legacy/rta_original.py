'''
rta.py

Purpose:
   This script performs the Response Time Analysis (RTA) of minimalistic real-time systems.
   The model follows the next assumptions:
   - Protected objects.
   - Periodic tasks that satisfy their periods.
   - Sporadic tasks that satisfy their periods.
   - Supports Immediate Ceiling Priority Protocol (ICPP).
   - Supports Priority Inheritance Protocol (PIP).
   - Offsets are NOT supported: All tasks are released at the same time.
   - Jitters are NOT supported.
   - There is NO support for distributed systems: E.g., CAN-Bus communication.

Copyright (C) 2024 Universidad Politécnica de Madrid

UPMSat-3 OBSW was developed by the Real-Time Systems Group at the
Universidad Politécnica de Madrid.
'''

import math
from typing import Self

PIP="PIP"   # Used by FreeRTOS
ICPP="ICPP" # Used by Ada (default for RTA_Solver)

# ----------
# -- Task --
# ----------

class Task:
    '''
    Class containing the task attributes as specified in the YAML config file
    '''

    def __init__(self, name, priority, task_type, period_ms, wcet_ms, deadline_ms) -> None:
        self.name = name
        self.priority = priority
        self.type = task_type
        self.period_ms = period_ms
        self.wcet_ms = wcet_ms
        self.deadline_ms = deadline_ms
        self.pr_objs = dict()

        self.rta_blocking_time_ms = 0
        self.rta_response_time_ms = 0
        self.rta_schedulable = False
        
    def access(self, po, time_ms) -> Self:
        self.pr_objs[po] = time_ms
        po.accessed_by(self)
        return self
    
    def access_time(self, to):
        return self.pr_objs[to]
    
    def as_row(self):
        return [
            self.name,
            self.type,
            self.priority,
            self.period_ms,
            self.wcet_ms,
            self.rta_blocking_time_ms,
            self.deadline_ms,
            self.rta_response_time_ms,
            "Yes" if self.rta_schedulable else "No"
        ]

# ----------------------
# -- Protected_Object --
# ----------------------

class Protected_Object:
    '''
    Class containing the attributes of a Protected Object
    '''

    def __init__(self, name) -> None:
        self.name = name
        self.tasks = set()
    
    def accessed_by(self, task: Task):
        self.tasks.add(task)
        
    def wcet(self):
        wcet = 0
        for t in self.tasks:
            wcet = max(wcet, t.access_time(to=self))
        return wcet

# ----------------
# -- RTA Solver --
# ----------------

class RTA_solver:
    def __init__(self, tasks, pr_objs, sync_protocol=ICPP) -> None:
        self.tasks = tasks
        self.pr_objs = pr_objs
        self.system_is_schedulable = False
        self.sync_protocol = sync_protocol

    def solve(self):
        
        self.tasks = sorted(self.tasks, key=lambda t : -t.priority)
        
        for t in self.tasks:
            self.calculate_blocking_time(t)
        
        self.system_is_schedulable = True
        for t in self.tasks:
            self.calculate_response_time(t)
            self.system_is_schedulable = self.system_is_schedulable and t.rta_schedulable
        
    def print(self):
        print("")
        header = ["Name", "Type", "Prio", "Period", "WCET", "Blocking", "Deadline", "Response", "Sched"]
        print('| {:>15} | {:>10} | {:>5} | {:>9} | {:>9} | {:>9} | {:>9} | {:>9} | {:>5} |'.format(*header))
        print('|-----------------|------------|-------|-----------|-----------|-----------|-----------|-----------|-------|')
        table = [t.as_row() for t in self.tasks]
        for row in table:
            print('| {:>15} | {:>10} | {:>5} | {:>9} | {:>9} | {:>9.6f} | {:>9} | {:>9.6f} | {:>5} |'.format(*row))
            
        print("")
        print(f"The system is schedulable? {self.system_is_schedulable}")
        print("")
        print("")
        
    def usage(self, po, task):
        ge_condition = False
        lt_condition = False
        for owner in po.tasks:
            ge_condition = ge_condition or owner.priority >= task.priority
            lt_condition = lt_condition or owner.priority < task.priority
        return ge_condition and lt_condition
        
    def calculate_blocking_time(self, task):
        b = 0
        for po in self.pr_objs:
            u = self.usage(po, task)
            if u:
                if self.sync_protocol == ICPP:
                    b = max(b, po.wcet())
                elif self.sync_protocol == PIP:
                    b += po.wcet()

        task.rta_blocking_time_ms = b
    
    def higher_priority_interference(self, task):
        hpif = 0
        for t in self.tasks:
            if t.name != task.name and t.priority > task.priority:
                hpif += math.ceil(float(task.rta_response_time_ms)/float(t.period_ms)) * t.wcet_ms
        return hpif
    
    def calculate_response_time(self, task):
        
        task.rta_response_time_ms = task.wcet_ms + task.rta_blocking_time_ms + self.higher_priority_interference(task)
        r_prev = task.rta_response_time_ms
        task.rta_response_time_ms = task.wcet_ms + task.rta_blocking_time_ms + self.higher_priority_interference(task)
        r_now = task.rta_response_time_ms
        
        while r_prev != r_now:
            r_prev = task.rta_response_time_ms
            task.rta_response_time_ms = task.wcet_ms + task.rta_blocking_time_ms + self.higher_priority_interference(task)
            r_now = task.rta_response_time_ms
        
        task.rta_schedulable = task.rta_response_time_ms <= task.deadline_ms
    
if __name__ == "__main__":
    
    # Example 1
    # ---------
    
    # Define Protected Objects (POs)
    po_1 = Protected_Object(name="po1")
    po_2 = Protected_Object(name="po2")
    po_3 = Protected_Object(name="po3")
    
    # Define Tasks & their access to POs
    task_1 = Task(name="Relax Vol.", priority=5, task_type="periodic",
                  period_ms=500, wcet_ms=30, deadline_ms=200)
    task_1.access(po_2,time_ms=7)
    
    task_2 = Task(name="Detect Vol.", priority=4, task_type="periodic",
                  period_ms=300, wcet_ms=20, deadline_ms=300)
    task_2.access(po_1,time_ms=5)
          
    task_3 = Task(name="Riesgos", priority=3, task_type="periodic",
                  period_ms=300, wcet_ms=50, deadline_ms=300)
    task_3.access(po_1,time_ms=7) \
          .access(po_2,time_ms=10)\
          .access(po_3,time_ms=10)
    
    task_4 = Task(name="Incli. Cabeza", priority=2, task_type="periodic",
                  period_ms=600, wcet_ms=100, deadline_ms=500)
    task_4.access(po_1,time_ms=10)\
          .access(po_2,time_ms=10)
          
    task_5 = Task(name="Det. Pul.", priority=1, task_type="sporadic",
                  period_ms=2000, wcet_ms=30, deadline_ms=2000)
    task_5.access(po_3,time_ms=10)\

    task_irq = Task(name="IRQ", priority=1000, task_type="periodic",
                    period_ms=2000, wcet_ms=20, deadline_ms=20)

    rta = RTA_solver(tasks={task_1, task_2, task_3, task_4, task_5, task_irq}, pr_objs={po_1, po_2, po_3})
    rta.solve()
    rta.print()
    
    # Example 2
    # ---------
    
    # Define Protected Objects (POs)
    po_1 = Protected_Object(name="Lock 1")
    po_2 = Protected_Object(name="Lock 2")
    po_3 = Protected_Object(name="Lock 3")
    
    # Define Tasks & their access to POs
    task_1 = Task(name="Task 1", priority=2, task_type="periodic",
                  period_ms=120, wcet_ms=25, deadline_ms=120)
    task_1.access(po_2,time_ms=10)\
          .access(po_3,time_ms=8)
    
    task_2 = Task(name="Task 2", priority=4, task_type="periodic",
                  period_ms=600, wcet_ms=20, deadline_ms=40)
    task_2.access(po_1,time_ms=7)\
          .access(po_2,time_ms=5)
          
    task_3 = Task(name="Task 3", priority=5, task_type="periodic",
                  period_ms=80, wcet_ms=8, deadline_ms=30)
    task_3.access(po_3,time_ms=4)
    
    task_4 = Task(name="Task 4", priority=3, task_type="periodic",
                  period_ms=50, wcet_ms=15, deadline_ms=50)
    task_4.access(po_1,time_ms=6)

    task_irq = Task(name="IRQ", priority=11, task_type="periodic",
                    period_ms=120, wcet_ms=2, deadline_ms=120)

    rta = RTA_solver(tasks={task_1, task_2, task_3, task_4, task_irq}, pr_objs={po_1, po_2, po_3})
    rta.solve()
    rta.print()
    
    # Result changes for PIP:
    rta = RTA_solver(tasks={task_1, task_2, task_3, task_4, task_irq}, pr_objs={po_1, po_2, po_3}, sync_protocol=PIP)
    rta.solve()
    rta.print()
