"""FIFO admission for resident turns; model/tool behavior remains agent-chosen."""
from collections import deque
import threading

class TurnQueue:
    def __init__(self,capacity):
        if type(capacity) is not int or capacity<1:raise ValueError('Use a positive turn capacity')
        self.capacity=capacity;self.active=0;self.waiting=deque();self.condition=threading.Condition()

    def acquire(self,*,cancel,key):
        ticket=object()
        with self.condition:
            self.waiting.append((ticket,key));self.condition.notify_all()
            try:
                while not cancel.is_set():
                    if self.waiting[0][0] is ticket and self.active<self.capacity:
                        self.waiting.popleft();self.active+=1;self.condition.notify_all();return True
                    self.condition.wait(.2)
                return False
            finally:
                # Cancellation must not strand a ticket at the queue's head.
                for item in self.waiting:
                    if item[0] is ticket:
                        self.waiting.remove(item);self.condition.notify_all();break

    def release(self):
        with self.condition:
            if not self.active:raise RuntimeError('No active turn slot to release')
            self.active-=1;self.condition.notify_all()

    def snapshot(self):
        with self.condition:return {'capacity':self.capacity,'active':self.active,'waiting':[key for _,key in self.waiting]}
