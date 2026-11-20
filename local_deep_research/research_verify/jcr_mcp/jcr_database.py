import asyncio
import sqlite3
import os
import sys
import json
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from pathlib import Path


# 配置常量
# 用相对 __file__ 的绝对路径，避免 MCP 客户端从其他 cwd 启动服务器时找不到 DB
DATABASE_PATH = str(Path(__file__).parent / "jcr.db")
DATA_UPDATE_URL = "https://raw.githubusercontent.com/hitfyd/ShowJCR/master/中科院分区表及JCR原始数据文件/"

@dataclass
class JournalInfo:
    """期刊信息数据类"""
    journal_name: str
    impact_factor: Optional[float] = None
    partition: Optional[str] = None
    category: Optional[str] = None
    warning_status: Optional[str] = None
    ccf_level: Optional[str] = None
    year: Optional[str] = None

def _table_year(table_name: str) -> Optional[str]:
    """从表名中提取年份，规则需与 _parse_journal_info 的分支顺序保持一致
    （更具体的前缀必须先于通用前缀判断，如 CCFT 先于 CCF）"""
    if table_name.startswith('XR') and 'Conferences' in table_name:
        digits = ''.join(ch for ch in table_name if ch.isdigit())
        return digits or None
    elif table_name.startswith('XR'):
        return table_name.replace('XR', '') or None
    elif table_name.startswith('FQBJCR'):
        return table_name.replace('FQBJCR', '') or None
    elif table_name.startswith('JCR'):
        return table_name.replace('JCR', '') or None
    elif table_name.startswith('GJQKYJMD'):
        return table_name.replace('GJQKYJMD', '') or None
    elif table_name.startswith('CCFT'):
        return table_name.replace('CCFT', '') or None
    elif table_name.startswith('CCF'):
        return table_name.replace('CCF', '') or None
    return None


class JCRDatabase:
    """JCR数据库管理类"""

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """初始化数据库"""
        if not os.path.exists(self.db_path):
            # 如果数据库不存在，创建基本表结构
            conn = sqlite3.connect(self.db_path)
            conn.close()

    def search_journal(self, journal_name: str, year: Optional[str] = None) -> List[JournalInfo]:
        """搜索期刊信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        results = []
        try:
            # 获取所有表名
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [table[0] for table in cursor.fetchall()]

            # 在各个表中搜索期刊
            for table in tables:
                try:
                    if year is not None and _table_year(table) != year:
                        continue

                    # 检查表结构
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = [col[1] for col in cursor.fetchall()]

                    if 'Journal' not in columns:
                        continue

                    # 构建查询语句
                    query = f"SELECT * FROM {table} WHERE Journal LIKE ? COLLATE NOCASE"
                    cursor.execute(query, (f"%{journal_name}%",))

                    rows = cursor.fetchall()
                    column_names = [description[0] for description in cursor.description]

                    for row in rows:
                        row_dict = dict(zip(column_names, row))
                        journal_info = self._parse_journal_info(row_dict, table)
                        if journal_info:
                            results.append(journal_info)

                except sqlite3.Error:
                    continue

        finally:
            conn.close()

        return results

    def _parse_journal_info(self, row_dict: Dict, table_name: str) -> Optional[JournalInfo]:
        """解析数据库行为期刊信息对象

        注意分支顺序：更具体的表名前缀（XRConferences / FQBJCR / CCFT）必须
        在通用前缀（XR / JCR / CCF）之前匹配，否则会被误归类。
        """
        def _clean(val):
            if val is None:
                return None
            s = str(val).strip()
            if s == '' or s.lower() == 'nan':
                return None
            return s

        def _is_top(val):
            """统一各表的 Top 标志位：XR 用 'Top'/空，FQBJCR 用 '是'/'否'，归一为布尔"""
            v = _clean(val)
            return v is not None and v in ('Top', '是', 'Yes', 'yes', 'True', 'true', 'TRUE')

        try:
            journal_name = row_dict.get('Journal', '')

            impact_factor = None
            partition = None
            category = None
            warning_status = None
            ccf_level = None
            year = None

            # 新锐期刊分区表 2026 的会议论文集子表（XR2026Conferences）
            if table_name.startswith('XR') and 'Conferences' in table_name:
                digits = ''.join(ch for ch in table_name if ch.isdigit())
                year = digits or None
                partition = _clean(row_dict.get('分区'))
                if partition and _is_top(row_dict.get('Top')):
                    partition = f"{partition}（Top）"
                abbrev = _clean(row_dict.get('会议缩写'))
                category = f"会议论文集（{abbrev}）" if abbrev else '会议论文集'

            # 新锐期刊分区表（XR2026 等）——含内嵌预警
            # 注意 XR 表的真实列名是「大类新锐分区」「预警标记」，与 FQBJCR 的「大类分区」不同
            elif table_name.startswith('XR'):
                year = table_name.replace('XR', '')
                partition = _clean(row_dict.get('大类新锐分区'))
                if partition and _is_top(row_dict.get('Top')):
                    partition = f"{partition}（Top）"
                category = _clean(row_dict.get('大类中文名')) or _clean(row_dict.get('大类英文名'))
                warning_status = _clean(row_dict.get('预警标记'))

            # 中科院分区表升级版（必须在 JCR 分支之前——'JCR' 是 'FQBJCR' 的子串）
            elif table_name.startswith('FQBJCR'):
                year = table_name.replace('FQBJCR', '')
                partition = _clean(row_dict.get('大类分区')) or _clean(row_dict.get('Partition'))
                if partition and _is_top(row_dict.get('Top')):
                    partition = f"{partition}（Top）"
                category = (_clean(row_dict.get('大类'))
                            or _clean(row_dict.get('领域'))
                            or _clean(row_dict.get('学科'))
                            or _clean(row_dict.get('Subject')))

            # JCR 影响因子（列名带年份后缀，如 IF(2024) / IF Quartile(2024)）
            # JCR2023 的 IF 列名实际是 ' IF(2023)'（带前导空格），故对列名做去空格归一化查找
            elif table_name.startswith('JCR'):
                year = table_name.replace('JCR', '')
                norm = {k.replace(' ', ''): v for k, v in row_dict.items() if isinstance(k, str)}
                impact_factor = (_clean(norm.get(f'IF({year})'))
                                 or _clean(row_dict.get('IF'))
                                 or _clean(row_dict.get('Impact Factor')))

                categories = []
                quartiles = []
                for i in range(1, 10):
                    c = _clean(norm.get(f'Category_{i}')) or _clean(row_dict.get(f'Category_{i}'))
                    q = _clean(norm.get(f'IFQuartile({year})_{i}')) or _clean(row_dict.get(f'IF Quartile({year})_{i}'))
                    if c:
                        categories.append(c)
                    if q:
                        quartiles.append(q)

                if categories:
                    category = '; '.join(categories)
                else:
                    category = _clean(row_dict.get('Category')) or _clean(row_dict.get('类别'))

                if quartiles:
                    partition = '; '.join(list(dict.fromkeys(quartiles)))
                else:
                    partition = (_clean(norm.get(f'IFQuartile({year})'))
                                 or _clean(row_dict.get('Quartile'))
                                 or _clean(row_dict.get('分区')))

            # 国际期刊预警名单（列名按年份变化：预警等级（YYYY年） / 预警原因YYYY年）
            elif table_name.startswith('GJQKYJMD'):
                year = table_name.replace('GJQKYJMD', '')
                # 取第二列（Journal 之外首个非空值）作为预警信息，兼容各年列名
                for k, v in row_dict.items():
                    if k == 'Journal':
                        continue
                    cleaned = _clean(v)
                    if cleaned:
                        warning_status = cleaned
                        break

            # 计算领域高质量科技期刊分级目录（必须在 CCF 分支之前）
            elif table_name.startswith('CCFT'):
                year = table_name.replace('CCFT', '')
                t_rank = _clean(row_dict.get('T分区'))
                ccf_level = f"{t_rank}（计算领域高质量科技期刊）" if t_rank else None
                category = _clean(row_dict.get('领域')) or '计算领域高质量科技期刊'

            # CCF 推荐国际学术会议和期刊目录
            elif table_name.startswith('CCF'):
                year = table_name.replace('CCF', '')
                ccf_type = _clean(row_dict.get('CCF推荐类型')) or _clean(row_dict.get('CCF Level'))
                ccf_cat = _clean(row_dict.get('CCF推荐类别（国际学术刊物/会议）'))
                if ccf_type and ccf_cat:
                    ccf_level = f"{ccf_type}（{ccf_cat}）"
                else:
                    ccf_level = ccf_type
                category = _clean(row_dict.get('领域')) or _clean(row_dict.get('Field'))

            return JournalInfo(
                journal_name=journal_name,
                impact_factor=impact_factor,
                partition=partition,
                category=category,
                warning_status=warning_status,
                ccf_level=ccf_level,
                year=year
            )

        except Exception:
            return None
