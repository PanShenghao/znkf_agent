"""
文件职能: MCP 服务端 —— 把电商业务能力（查订单/物流/优惠/商品/售后）暴露成工具。
带容错：参数校验 + 重试 + 友好降级（不把技术错误暴露给用户）。
"""
import os
import json
import time
import pymysql
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path)

mcp = FastMCP("ShopPlatformMCPServer")

MAX_RETRIES = 2   # 数据库查询最多重试 2 次


def get_db_connection():
    """连 MySQL（结果以字典返回）"""
    return pymysql.connect(
        host=os.getenv('MYSQL_HOST', "127.0.0.1"),
        port=int(os.getenv('MYSQL_PORT', 3306)),
        user=os.getenv('MYSQL_USER', "root"),
        password=os.getenv('MYSQL_PASSWORD', ""),
        database=os.getenv("MYSQL_DATABASE", "digital_shop"),
        cursorclass=pymysql.cursors.DictCursor,
    )


def _friendly_error():
    """把技术错误转成业务友好的提示（不暴露底层细节给用户）"""
    return json.dumps({"status": "error", "message": "系统繁忙，请稍后重试"}, ensure_ascii=False)


def _execute_with_retry(sql, params):
    """带重试的数据库查询：失败自动重试，都失败才抛异常"""
    for attempt in range(MAX_RETRIES + 1):
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(0.3 * (attempt + 1))   # 递增等待后重试
                continue
            raise   # 重试完还失败，才抛出
        finally:
            if conn is not None and conn.open:
                conn.close()


@mcp.tool()
def query_user_orders(user_id: str, limit: int = 5) -> str:
    """查询用户的订单记录。
    Args:
        user_id: [系统注入] 用户的唯一标识，不允许模型伪造
        limit: [模型生成] 返回的最大记录数，默认 5，范围 1-50
    """
    # 参数校验
    if not isinstance(limit, int) or limit < 1 or limit > 50:
        return json.dumps({"status": "error", "message": "limit 参数需在 1-50 之间"}, ensure_ascii=False)

    try:
        results = _execute_with_retry(
            "SELECT order_id, product_name, amount, status, created_at "
            "FROM orders WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
            (user_id, limit)
        )
    except Exception:
        return _friendly_error()

    if not results:
        return json.dumps({"status": "success", "message": "该用户暂无订单"}, ensure_ascii=False)
    return json.dumps({"status": "success", "data": results}, ensure_ascii=False, default=str)


@mcp.tool()
def query_logistics(order_id: str) -> str:
    """根据订单号查询物流进度（用户通常只有订单号，没有物流单号）。
    Args:
        order_id: [模型生成] 订单号，如 "ORD-1001-001"
    """
    if not order_id or not order_id.strip():
        return json.dumps({"status": "error", "message": "请提供订单号"}, ensure_ascii=False)

    try:
        results = _execute_with_retry(
            "SELECT tracking_no, order_id, carrier, status, updated_at FROM logistics WHERE order_id = %s",
            (order_id.strip(),)
        )
    except Exception:
        return _friendly_error()

    if not results:
        return json.dumps({"status": "error", "message": "未查到该订单的物流信息"}, ensure_ascii=False)
    return json.dumps({"status": "success", "data": results[0]}, ensure_ascii=False, default=str)


@mcp.tool()
def get_coupons() -> str:
    """查询当前所有可用的优惠券。"""
    try:
        results = _execute_with_retry(
            "SELECT coupon_id, name, discount_type, discount_value, condition_amount FROM coupons", ()
        )
    except Exception:
        return _friendly_error()

    if not results:
        return json.dumps({"status": "success", "message": "暂无可用优惠券"}, ensure_ascii=False)
    return json.dumps({"status": "success", "data": results}, ensure_ascii=False, default=str)


@mcp.tool()
def search_product_catalog(keyword: str) -> str:
    """按关键词模糊搜索商品（按品牌、品类、名称搜）。
    Args:
        keyword: [模型生成] 搜索关键词，如 "手机"、"苹果"、"小米"
    """
    if not keyword or not keyword.strip():
        return json.dumps({"status": "error", "message": "请提供搜索关键词"}, ensure_ascii=False)

    try:
        results = _execute_with_retry(
            "SELECT product_id, name, brand, category, price, specs FROM products "
            "WHERE name LIKE %s OR brand LIKE %s OR category LIKE %s",
            (f"%{keyword.strip()}%",) * 3
        )
    except Exception:
        return _friendly_error()

    if not results:
        return json.dumps({"status": "not_found", "message": f"未找到与'{keyword}'相关的商品"}, ensure_ascii=False)
    return json.dumps({"status": "success", "data": results}, ensure_ascii=False, default=str)


@mcp.tool()
def query_after_sales(user_id: str) -> str:
    """查询用户的售后单（退换货/维修记录）。
    Args:
        user_id: [系统注入] 用户的唯一标识，不允许模型伪造
    """
    try:
        results = _execute_with_retry(
            "SELECT as_id, order_id, type, status FROM after_sales WHERE user_id = %s", (user_id,)
        )
    except Exception:
        return _friendly_error()

    if not results:
        return json.dumps({"status": "success", "message": "该用户暂无售后单"}, ensure_ascii=False)
    return json.dumps({"status": "success", "data": results}, ensure_ascii=False, default=str)


if __name__ == "__main__":
    mcp.run()
