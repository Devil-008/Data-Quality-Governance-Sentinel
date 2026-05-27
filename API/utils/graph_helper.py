import os
from arango import ArangoClient
from utils.common import logger

class GraphManager:
    def __init__(self):
        self.host = os.getenv("ARANGO_URL", "http://157.173.221.226:8529")
        self.username = os.getenv("ARANGO_USER", "root")
        self.password = os.getenv("ARANGO_PASSWORD", "Aiinhome@2026")
        self.db_name = os.getenv("ARANGO_DB", "mpna_graph")

        self.client = ArangoClient(hosts=self.host)
        self.db = None
        self._connect()

    def _connect(self):
        try:
            self.db = self.client.db(
                self.db_name,
                username=self.username,
                password=self.password
            )
            # Check connection
            self.db.version()
            logger.info("Connected to ArangoDB: %s", self.host)
            self._init_schema()
        except Exception as e:
            logger.error("Failed to connect to ArangoDB: %s", e)
            self.db = None

    def _init_schema(self):
        if not self.db:
            return
        
        # Collections
        vertices = ["Rulebook", "Rule", "Dataset", "Column", "Alert"]
        edges = ["CONTAINS_RULE", "APPLIES_TO", "HAS_COLUMN", "RAISED_ON", "VIOLATES"]
        
        for v in vertices:
            if not self.db.has_collection(v):
                self.db.create_collection(v)
        
        for e in edges:
            if not self.db.has_collection(e):
                self.db.create_collection(e, edge=True)

    def insert_rulebook(self, rulebook_id: int, name: str, content: str, summary: str = ""):
        if not self.db: return
        col = self.db.collection("Rulebook")
        doc = {"_key": str(rulebook_id), "name": name, "content": content[:1000], "summary": summary}
        if not col.has(str(rulebook_id)):
            col.insert(doc)
        else:
            col.update(doc)

    def insert_rule(self, rule_id: str, rulebook_id: int, rule_text: str):
        if not self.db: return
        col = self.db.collection("Rule")
        doc = {"_key": rule_id, "text": rule_text}
        if not col.has(rule_id):
            col.insert(doc)
        else:
            col.update(doc)
        
        self.create_edge("CONTAINS_RULE", f"Rulebook/{rulebook_id}", f"Rule/{rule_id}")

    def insert_dataset(self, dataset_id: int, name: str):
        if not self.db: return
        col = self.db.collection("Dataset")
        doc = {"_key": str(dataset_id), "name": name}
        if not col.has(str(dataset_id)):
            col.insert(doc)

    def insert_alert(self, alert_id: int, title: str, message: str, dataset_id: int, rule_id: str = None):
        if not self.db: return
        col = self.db.collection("Alert")
        doc = {"_key": str(alert_id), "title": title, "message": message}
        if not col.has(str(alert_id)):
            col.insert(doc)
        
        if dataset_id:
            self.insert_dataset(dataset_id, f"Dataset_{dataset_id}")
            self.create_edge("RAISED_ON", f"Alert/{alert_id}", f"Dataset/{dataset_id}")
            
        if rule_id:
            self.create_edge("VIOLATES", f"Alert/{alert_id}", f"Rule/{rule_id}")

    def create_edge(self, edge_col: str, from_vert: str, to_vert: str):
        if not self.db: return
        col = self.db.collection(edge_col)
        # Unique key for edge
        edge_key = f"{from_vert.replace('/', '_')}-{to_vert.replace('/', '_')}"
        if not col.has(edge_key):
            try:
                col.insert({"_key": edge_key, "_from": from_vert, "_to": to_vert})
            except Exception as e:
                logger.error("Error creating edge %s: %s", edge_col, e)

    def get_alert_context(self, alert_id: int) -> str:
        """Retrieves graph neighborhood context for a specific alert."""
        if not self.db: return ""
        try:
            aql = f"""
            FOR alert IN Alert
                FILTER alert._key == '{alert_id}'
                FOR v, e IN 1..2 ANY alert VIOLATES, RAISED_ON
                RETURN DISTINCT v
            """
            cursor = self.db.aql.execute(aql)
            nodes = [doc for doc in cursor]
            
            if not nodes:
                return "No historical graph context found for this alert."
            
            context = f"Graph Context for Alert {alert_id}:\n"
            for n in nodes:
                if n.get("text"):
                    context += f"- Related Rule: {n.get('text')}\n"
                elif n.get("name"):
                    context += f"- Related Entity: {n.get('name')}\n"
                elif n.get("title") and n.get("_key") != str(alert_id):
                    context += f"- Historical Alert on similar nodes: {n.get('title')}\n"
            return context
        except Exception as e:
            logger.error("Graph query failed: %s", e)
            return ""

# Singleton instance
graph_db = GraphManager()
