"""
文件职能：商品咨询的「查数据」工具：查知识图谱（Neo4j），回答「品牌/品类/商品之间的关系、精确参数」这类问题。
策略：① 先做确定性名称匹配（query 含已知商品名 → 直接 MATCH 该商品，稳定不靠 LLM 生成 Cypher）；
      ② 复杂/多跳关系才交给 GraphCypherQAChain（LLM 生成 Cypher，固有脆弱，仅作兜底）。
"""
from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_core.tools import tool

from config import get_settings
from core.resilience.llm import get_llm
from core.grounding import record_evidence

_graph_instance = None
_graph_chain_instance = None
_known_products = None
_known_brands = None
_known_categories = None


def _get_graph():
    global _graph_instance
    if _graph_instance is None:
        settings = get_settings()
        _graph_instance = Neo4jGraph(
            url=settings.neo4j_uri,
            username=settings.neo4j_user,
            password=settings.neo4j_password,
        )
        _graph_instance.refresh_schema()
    return _graph_instance


def _get_graph_chain():
    global _graph_chain_instance
    if _graph_chain_instance is None:
        # 安全提示：allow_dangerous_requests=True 会直接执行 LLM 生成的 Cypher。
        # 生产环境应给 Neo4j 配置只读账号。这里仅作复杂关系的兜底。
        _graph_chain_instance = GraphCypherQAChain.from_llm(
            llm=get_llm(temperature=0),
            graph=_get_graph(),
            allow_dangerous_requests=True,
        )
    return _graph_chain_instance


def _get_known_products():
    """所有商品名（单例缓存），用于确定性名称匹配。"""
    global _known_products
    if _known_products is None:
        try:
            rows = _get_graph().query("MATCH (n:Product) RETURN n.name AS name")
            _known_products = [r["name"] for r in rows]
        except Exception:
            _known_products = []
    return _known_products


def _get_known_brands():
    """所有品牌名（单例缓存）。"""
    global _known_brands
    if _known_brands is None:
        try:
            rows = _get_graph().query("MATCH (n:Brand) RETURN n.name AS name")
            _known_brands = [r["name"] for r in rows]
        except Exception:
            _known_brands = []
    return _known_brands


def _get_known_categories():
    """所有品类名（单例缓存）。"""
    global _known_categories
    if _known_categories is None:
        try:
            rows = _get_graph().query("MATCH (n:Category) RETURN n.name AS name")
            _known_categories = [r["name"] for r in rows]
        except Exception:
            _known_categories = []
    return _known_categories


def _deterministic_lookup(query: str) -> str | None:
    """确定性查询：① 商品名精确匹配 ② 品牌/品类关系查询（不靠 LLM 生成 Cypher）。"""
    graph = _get_graph()
    # ① 商品名精确匹配
    for name in _get_known_products():
        if name in query:
            try:
                rows = graph.query("MATCH (n:Product {name: $name}) RETURN n", params={"name": name})
                if rows:
                    node = rows[0]["n"]
                    props = {k: v for k, v in node.items() if k not in ("id", "name")}
                    lines = [f"- {k}: {v}" for k, v in props.items()]
                    return f"【{name}】\n" + "\n".join(lines)
            except Exception:
                pass
    # ②/③ 品牌/品类关系查询（如「小米有哪些手机」「耳机有哪些」）
    if any(k in query for k in ("有哪些", "有什么", "哪些", "什么", "推荐", "产品", "商品")):
        for brand in _get_known_brands():
            if brand in query:
                try:
                    rows = graph.query(
                        "MATCH (p:Product)-[:BELONGS_TO]->(b:Brand {name: $name}) "
                        "RETURN p.name AS name, p.price AS price ORDER BY p.price",
                        params={"name": brand})
                    if rows:
                        lines = [f"- {r['name']}: ¥{r['price']}" for r in rows]
                        return f"【{brand} 品牌商品】\n" + "\n".join(lines)
                except Exception:
                    pass
        for cat in _get_known_categories():
            if cat in query:
                try:
                    rows = graph.query(
                        "MATCH (p:Product)-[:BELONGS_TO]->(c:Category {name: $name}) "
                        "RETURN p.name AS name, p.price AS price ORDER BY p.price",
                        params={"name": cat})
                    if rows:
                        lines = [f"- {r['name']}: ¥{r['price']}" for r in rows]
                        return f"【{cat} 品类商品】\n" + "\n".join(lines)
                except Exception:
                    pass
    return None


@tool
def query_knowledge_graph(query: str) -> str:
    """
    查询数码商品知识图谱。
    当用户询问商品参数、品牌系列关系、多跳关系时，使用此工具。
    若返回「未找到」，必须如实告知用户无法确认，严禁编造。
    """
    # ① 确定性名称匹配（稳定优先）
    text = _deterministic_lookup(query)
    if text:
        record_evidence("knowledge_graph", found=True, score=1.0)
        return text

    # ② 复杂/多跳关系 → GraphCypherQAChain
    chain = _get_graph_chain()
    try:
        result = chain.invoke({"query": query})  # 自然语言→Cypher→查询→自然语言
        text = result.get("result", "")
        found = bool(text) and "未找到" not in text and "未查到" not in text
        record_evidence("knowledge_graph", found=found, score=1.0 if found else 0.0)
        return text if text else "未找到相关图谱信息。该商品可能不在知识图谱中，请改用 query_vector_db 查询商品文档。"
    except Exception:
        record_evidence("knowledge_graph", found=False, score=0.0)
        return "查询知识图谱时发生错误，请稍后重试！"
