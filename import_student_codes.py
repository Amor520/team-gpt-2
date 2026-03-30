"""
导入学号兑换码

将学号写入 redemption_codes，作为可重复使用的兑换码：
- 默认 30 天内最多兑换 3 次
- 张宇不限次数
"""
import asyncio
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal, init_db
from app.db_migrations import run_auto_migration
from app.models import RedemptionCode


STUDENT_CODES = [
    ("8208230107", "周志鹏", 3, 30),
    ("8208230109", "汪钦", 3, 30),
    ("8208230405", "郑苏远", 3, 30),
    ("8208230411", "朱宏喆", 3, 30),
    ("8208230605", "徐志涛", 3, 30),
    ("8208230617", "曾海洋", 3, 30),
    ("8208230618", "陆宣羽", 3, 30),
    ("8208231012", "邓宏博", 3, 30),
    ("8208230509", "刘秉承", 3, 30),
    ("8208231405", "张圣源", 3, 30),
    ("8208231604", "吴子健", 3, 30),
    ("8208231631", "赵逸翔", 3, 30),
    ("8208230311", "赵祥宇", 3, 30),
    ("8208231011", "余军钒", 3, 30),
    ("8208231428", "朱彦臣", 3, 30),
    ("8208231525", "左嘉帅", 3, 30),
    ("8208230930", "曾雪松", 3, 30),
    ("8208231003", "刘小睿", 3, 30),
    ("8208231009", "鲁翰宇", 3, 30),
    ("8208231325", "张宇", -1, None),
    ("8208230123", "庄欣怡", 3, 30),
    ("8208230231", "黄璿恩", 3, 30),
    ("8208231429", "江昕芮", 3, 30),
    ("8208231029", "丽达·奴尔布拉提", 3, 30),
    ("8208231202", "贾璇", 3, 30),
    ("8208231421", "王美蘋", 3, 30),
    ("8208231427", "曾沚玉", 3, 30),
    ("8202230216", "梁焯然", 3, 30),
    ("8208220201", "蔡明轩", 3, 30),
    ("L208230733", "罗达", 3, 30),
]


async def main() -> None:
    db_file = settings.database_url.split("///")[-1]
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)

    await init_db()
    run_auto_migration()

    created = 0
    updated = 0

    async with AsyncSessionLocal() as session:
        for code, name, max_redemptions, window_days in STUDENT_CODES:
            result = await session.execute(
                select(RedemptionCode).where(RedemptionCode.code == code)
            )
            existing = result.scalar_one_or_none()

            if existing is None:
                existing = RedemptionCode(
                    code=code,
                    status="unused",
                )
                session.add(existing)
                created += 1
            else:
                updated += 1

            existing.pool_type = "normal"
            existing.reusable_by_seat = True
            existing.max_redemptions = max_redemptions
            existing.redemption_window_days = window_days
            existing.has_warranty = False
            existing.warranty_days = 0
            existing.expires_at = None

            if not existing.used_at and existing.status == "expired":
                existing.status = "unused"

            limit_text = "不限次数" if max_redemptions < 0 else f"{max_redemptions} 次/{window_days} 天"
            print(f"[OK] {code} {name}: {limit_text}")

        await session.commit()

    print(f"导入完成，新增 {created} 个，更新 {updated} 个。")


if __name__ == "__main__":
    asyncio.run(main())
