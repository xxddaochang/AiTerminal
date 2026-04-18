import os
import pathlib


class FileService:
    # 单文件最大展示字节数 (1 MiB)
    MAX_READ_BYTES = 1024 * 1024
    # 单次写入最大字节数 (5 MiB)
    MAX_WRITE_BYTES = 5 * 1024 * 1024

    def __init__(self, root_dir: str = None, allow_hidden: bool = False):
        if not root_dir:
            self.root_dir = os.path.expanduser("~")
        else:
            self.root_dir = root_dir
        # 预解析 root 的真实路径（解引用符号链接），避免每次重复计算
        self._root_real = os.path.realpath(self.root_dir)
        self.allow_hidden = allow_hidden

    # ---------- 内部：路径安全校验 ----------

    def _resolve_safe(self, path: str, *, must_exist: bool = True) -> str:
        """
        把用户传入的相对路径解析为安全的绝对路径。
        防御：
          - 绝对路径（以 / 开头）拒绝
          - .. 路径遍历拒绝
          - 符号链接指向 root 之外拒绝（通过 realpath 检测）
        """
        if path is None:
            raise ValueError("path is required")
        # 拒绝绝对路径
        if os.path.isabs(path):
            raise ValueError("Access Denied: absolute path not allowed")
        # 拼接后做 realpath —— 会解析软链，防止 `link -> /etc/passwd` 之类逃逸
        joined = os.path.join(self._root_real, path)
        real = os.path.realpath(joined)
        # 使用 commonpath 判断归属，比 startswith 更严谨（后者对 /home/userX vs /home/user 会误判）
        try:
            common = os.path.commonpath([self._root_real, real])
        except ValueError:
            # 不同盘符等异常（Windows）
            raise ValueError("Access Denied: path outside root")
        if common != self._root_real:
            raise ValueError("Access Denied: path outside root")
        if must_exist and not os.path.exists(real):
            raise FileNotFoundError(f"Path not found: {path}")
        return real

    # ---------- 对外 API ----------

    def list_dir(self, path: str = "", show_hidden: bool = None):
        """
        列出目录内容。path 相对于 root_dir。
        show_hidden: 覆盖实例级 allow_hidden；默认 None 时使用实例设置。
        """
        target_path = self._resolve_safe(path or "", must_exist=True)
        if not os.path.isdir(target_path):
            raise ValueError("Not a directory")

        hidden = self.allow_hidden if show_hidden is None else show_hidden

        items = []
        try:
            with os.scandir(target_path) as it:
                for entry in it:
                    if (not hidden) and entry.name.startswith("."):
                        continue
                    try:
                        is_dir = entry.is_dir()
                        size = entry.stat().st_size if entry.is_file() else 0
                    except OSError:
                        # broken symlink 或权限问题
                        continue
                    items.append({
                        "name": entry.name,
                        "path": os.path.join(path, entry.name) if path else entry.name,
                        "type": "dir" if is_dir else "file",
                        "size": size,
                    })
        except PermissionError:
            pass  # 跳过无法读取的文件夹

        # 排序: 文件夹在前, 然后是文件
        items.sort(key=lambda x: (0 if x["type"] == "dir" else 1, x["name"].lower()))
        return items

    def read_file(self, path: str):
        target_path = self._resolve_safe(path, must_exist=True)

        if not os.path.isfile(target_path):
            raise FileNotFoundError("Not a file")

        if os.path.getsize(target_path) > self.MAX_READ_BYTES:
            return "Error: File too large to display"

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            return "Error: Binary file not supported"
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def save_file(self, path: str, content: str, force: bool = False) -> dict:
        """
        写入文件。必须是 root 内的相对路径；父目录必须已存在（不会为你递归创建，避免意外写出深层目录）。
        force: 目标存在时是否覆盖。
        """
        if not isinstance(content, str):
            raise ValueError("content must be a string")
        if len(content.encode("utf-8", errors="ignore")) > self.MAX_WRITE_BYTES:
            raise ValueError(
                f"content too large (> {self.MAX_WRITE_BYTES // 1024 // 1024} MiB)"
            )

        # 对写入场景，路径允许尚不存在；但其父目录必须存在并位于 root 内
        if os.path.isabs(path):
            raise ValueError("Access Denied: absolute path not allowed")
        joined = os.path.join(self._root_real, path)
        # 不直接对 joined 取 realpath（文件可能还不存在），而是对父目录取
        parent_joined = os.path.dirname(joined) or self._root_real
        parent_real = os.path.realpath(parent_joined)
        try:
            common = os.path.commonpath([self._root_real, parent_real])
        except ValueError:
            raise ValueError("Access Denied: path outside root")
        if common != self._root_real:
            raise ValueError("Access Denied: path outside root")
        if not os.path.isdir(parent_real):
            raise FileNotFoundError(f"Parent directory does not exist: {os.path.dirname(path)}")

        target_real = os.path.join(parent_real, os.path.basename(path))

        # 如果 target 已存在且是符号链接，额外校验其指向
        if os.path.islink(target_real):
            link_real = os.path.realpath(target_real)
            try:
                if os.path.commonpath([self._root_real, link_real]) != self._root_real:
                    raise ValueError("Access Denied: symlink target outside root")
            except ValueError:
                raise ValueError("Access Denied: symlink target outside root")

        if os.path.exists(target_real) and not force:
            raise ValueError("File exists (use force=true to overwrite)")

        with open(target_real, "w", encoding="utf-8") as f:
            f.write(content)

        return {"status": "ok", "path": path}
