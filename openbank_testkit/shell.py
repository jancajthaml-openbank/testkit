#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import subprocess
import threading
import signal
import time
import os
import re


class Deadline(threading.Thread):

  def __init__(self, timeout, callback):
    super().__init__(daemon=True)
    self.__timeout = timeout
    self.__callback = callback
    self.__cancelled = threading.Event()

  def run(self):
    deadline = time.monotonic() + self.__timeout
    while not self.__cancelled.wait(deadline - time.monotonic()):
      if not self.__cancelled.is_set() and deadline <= time.monotonic():
        return self.__callback()

  def cancel(self):
    self.__cancelled.set()
    self.join()


class Shell(object):

  @staticmethod
  def run(command, timeout=60):
    ansi_escape = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]', flags=re.IGNORECASE)
    try:
      p = subprocess.Popen(
        command,
        shell=False,
        stdin=None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True
      )

      def kill():
        for sig in [signal.SIGTERM, signal.SIGQUIT, signal.SIGKILL, signal.SIGKILL]:
          if p.poll():
            break
          try:
            os.kill(p.pid, sig)
          except OSError:
            break

      deadline = Deadline(timeout, callback=kill)
      deadline.start()
      (result, error) = p.communicate()
      deadline.cancel()

      result = result.decode('utf-8').strip() if result else ''
      result = ansi_escape.sub('', result)
      error = error.decode('utf-8').strip() if error else ''
      error = ansi_escape.sub('', error)

      if p.returncode == 0:
        code = 'OK'
      elif p.returncode < 0:
        code = signal.Signals(-p.returncode).name
      else:
        code = signal.Signals(p.returncode).name

      del p

      return (code, result, error)
    except subprocess.CalledProcessError:
      return ('SIGQUIT', None, None)
