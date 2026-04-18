import os
import sys
import ptyprocess
import select
import asyncio
import signal

class PTYService:
    def __init__(self, cols=80, rows=24):
        self.cols = cols
        self.rows = rows
        self.process = None
        self.fd = None

    def start(self):
        # 确定 Shell
        shell = os.environ.get("SHELL", "/bin/bash")
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        self.process = ptyprocess.PtyProcess.spawn(
            [shell],
            env=env,
            cwd=os.path.expanduser("~"),
            dimensions=(self.rows, self.cols)
        )
        self.fd = self.process.fd

    def resize(self, cols, rows):
        if self.process:
            self.process.setwinsize(rows, cols)

    def write(self, data: str):
        if self.process:
            self.process.write(data.encode('utf-8'))

    async def read_generator(self):
        """从 PTY stdout 生成数据"""
        loop = asyncio.get_event_loop()
        while True:
            try:
                # 使用 run_in_executor 避免阻塞事件循环
                data = await loop.run_in_executor(None, self._read_blocking)
                
                if data is None: # 进程已结束
                    print("[PTY] Process finished")
                    break
                
                if len(data) == 0: # 超时/无数据
                    continue
                    
                text = data.decode('utf-8', errors='ignore')
                # print(f"[PTY] Read {len(text)} chars: {text!r}") 
                yield text
            except (IOError, EOFError):
                break

    def _read_blocking(self):
        # 进程已被 stop() 清理
        if self.fd is None or self.process is None:
            return None
        # 带超时的 Select，以便我们可以检查进程是否存活
        try:
            r, _, _ = select.select([self.fd], [], [], 0.1)
        except (ValueError, OSError):
            return None
        if self.fd in r:
            try:
                return os.read(self.fd, 1024)
            except OSError:
                return None
        elif not self.process or not self.process.isalive():
            return None
        return b""  # 超时，继续尝试

    def stop(self):
        if self.process:
            try:
                self.process.terminate(force=True)
            except Exception:
                pass
            finally:
                self.process = None
                self.fd = None

    def get_cwd(self) -> str:
        """获取 PTY 进程 Shell 的当前工作目录。

        Linux: 直接读 /proc/{pid}/cwd
        macOS / 其他 Unix: 退路调用 lsof（若可用），否则返回 HOME
        Windows: 不支持，返回 HOME
        """
        if not self.process or not self.process.isalive():
            return os.path.expanduser("~")
        pid = self.process.pid
        # Linux
        if sys.platform.startswith("linux"):
            try:
                return os.readlink(f"/proc/{pid}/cwd")
            except Exception:
                return os.path.expanduser("~")
        # macOS / BSD：尝试 lsof
        if sys.platform == "darwin":
            try:
                import subprocess
                out = subprocess.run(
                    ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                    capture_output=True, text=True, timeout=2,
                )
                for line in out.stdout.splitlines():
                    if line.startswith("n"):
                        return line[1:]
            except Exception:
                pass
        return os.path.expanduser("~")
