# 用 dulwich（纯 Python git）为 V0.1 定稿做首次快照：init + commit + 注解 tag v0.1.0
# 生成的是标准 git 仓库，以后装了 Git CLI 可继续正常使用。
import os
import sys

from dulwich import porcelain
from dulwich.repo import Repo

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NAME = "Smartoken Dev"
EMAIL = "dev@smartoken.local"


def main() -> int:
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        porcelain.init(ROOT)
        print("git init: ok")
    repo = Repo(ROOT)
    cfg = repo.get_config()
    cfg.set((b"user",), b"name", NAME.encode())
    cfg.set((b"user",), b"email", EMAIL.encode())
    cfg.write_to_path()

    author_id = f"{NAME} <{EMAIL}>"
    porcelain.add(repo, ".")
    porcelain.commit(
        repo,
        message=(
            "release(v0.1.0): Smartoken 定稿首版\n\n"
            "- 任务感知路由内核(daemon): auto/custom 策略、审计+live、7天留存\n"
            "- PySide6 桌面壳: 服务/API、模型与策略、用量看板(深色科技风)\n"
            "- 36 tests passed\n"
        ).encode("utf-8"),
        author=author_id, committer=author_id,
    )
    head = repo.head()
    print("HEAD:", head.decode())

    # 注解 tag v0.1.0（优先 porcelain.tag_create，低版本退化手工建对象）
    try:
        porcelain.tag_create(
            repo, b"v0.1.0", objectish=head,
            tagger=author_id,
            message="Smartoken v0.1.0 first release".encode("utf-8"),
        )
        print("tag v0.1.0: ok")
    except (AttributeError, TypeError):
        from dulwich.objects import Tag
        tag = Tag()
        tag.tagger = author_id.encode()
        tag.message = "Smartoken v0.1.0 first release\n".encode("utf-8")
        tag.name = b"v0.1.0"
        tag.object = (b"commit", head)
        tag.tagger_time = 0
        tag.tagger_timezone = 480        # +0800 in minutes
        sha = repo.object_store.add_object(tag)
        repo.refs[b"refs/tags/v0.1.0"] = sha
        print("tag v0.1.0: ok (manual)")

    # 校验
    tags = list(repo.refs.keys(b"refs/tags/"))
    print("tags:", [t.decode() for t in tags])
    entries = [os.path.basename(e.path_bytes) for e in repo.open_index()]
    print(f"tracked files: {len(entries)}")
    for h in repo.head().decode(), None:
        pass
    msg = repo[repo.head()].message.decode(errors="replace").splitlines()[0]
    print("commit msg:", msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
