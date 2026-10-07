"""벡터 저장소: 분석 시 관련 과거 기사를 찾기 위한 ChromaDB 래퍼."""
import os
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
import logging

from config import Config

logger = logging.getLogger(__name__)

CHROMA_PATH = os.path.join(Config.HDD_BASE_PATH, 'chromadb')
CHROMA_FALLBACK = os.path.join(Config.LOCAL_FALLBACK_PATH, 'chromadb')
EMBEDDING_MODEL = 'intfloat/multilingual-e5-small'


class VectorStore:
    def __init__(self):
        # 외장이 붙어 있을 때만 그쪽에 쓰고, 아니면 로컬 폴백에 쓴다
        path = CHROMA_PATH if Config.EXTERNAL_STORAGE_ACTIVE else CHROMA_FALLBACK
        os.makedirs(path, exist_ok=True)
        self.client = chromadb.PersistentClient(path=path)
        self._ef = SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL,
        )
        self.collection = self.client.get_or_create_collection(
            name='news_articles',
            embedding_function=self._ef,
            metadata={'hnsw:space': 'cosine'},
        )
        logger.info(f"VectorStore 초기화: {path} | 모델: {EMBEDDING_MODEL} ({self.collection.count()}건)")

    def add_article(self, article):
        """기사를 벡터DB에 추가"""
        aid = article.get('id', '')
        if not aid:
            return
        title = article.get('title', '')
        snippet = article.get('content_snippet', '')[:500]
        source = article.get('source', '')
        category = article.get('category', '')
        date = article.get('published_at', '')[:10]

        doc = f"{title}\n{snippet}"
        if not doc.strip():
            return

        try:
            self.collection.upsert(
                ids=[aid],
                documents=[doc],
                metadatas=[{
                    'source': source,
                    'category': category,
                    'date': date,
                    'title': title,
                }],
            )
        except Exception as e:
            logger.error(f"벡터 저장 실패 [{aid}]: {e}")

    def add_articles(self, articles):
        """여러 기사를 한번에 추가"""
        ids, docs, metas = [], [], []
        for a in articles:
            aid = a.get('id', '')
            title = a.get('title', '')
            snippet = a.get('content_snippet', '')[:500]
            doc = f"{title}\n{snippet}"
            if not aid or not doc.strip():
                continue
            ids.append(aid)
            docs.append(doc)
            metas.append({
                'source': a.get('source', ''),
                'category': a.get('category', ''),
                'date': a.get('published_at', '')[:10],
                'title': title,
            })

        if not ids:
            return 0

        # ChromaDB batch limit
        batch = 500
        for i in range(0, len(ids), batch):
            try:
                self.collection.upsert(
                    ids=ids[i:i+batch],
                    documents=docs[i:i+batch],
                    metadatas=metas[i:i+batch],
                )
            except Exception as e:
                logger.error(f"벡터 배치 저장 실패: {e}")

        logger.info(f"벡터DB 저장: {len(ids)}건 (총 {self.collection.count()}건)")
        return len(ids)

    def search(self, query, n_results=10, category=None, date=None):
        """유사 기사 검색
        category: 단일 문자열 또는 리스트 (['politics', 'general'])
        """
        where_parts = []
        if category:
            if isinstance(category, list) and len(category) > 1:
                where_parts.append({'category': {'$in': category}})
            elif isinstance(category, list):
                where_parts.append({'category': category[0]})
            else:
                where_parts.append({'category': category})
        if date:
            where_parts.append({'date': date})

        if len(where_parts) == 0:
            where = None
        elif len(where_parts) == 1:
            where = where_parts[0]
        else:
            where = {'$and': where_parts}

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
            )
            articles = []
            if results and results['metadatas']:
                for i, meta in enumerate(results['metadatas'][0]):
                    articles.append({
                        'id': results['ids'][0][i],
                        'title': meta.get('title', ''),
                        'source': meta.get('source', ''),
                        'category': meta.get('category', ''),
                        'date': meta.get('date', ''),
                        'distance': results['distances'][0][i] if results.get('distances') else None,
                    })
            return articles
        except Exception as e:
            logger.error(f"벡터 검색 실패: {e}")
            return []

    def search_related(self, theme_title, keywords, n_results=15, category=None):
        """테마 관련 과거 기사 검색 (분석용)
        category 지정 시 해당 카테고리 우선, 결과 부족하면 전체에서 보강
        """
        query = f"{theme_title} {' '.join(keywords[:5])}"
        if not category:
            return self.search(query, n_results=n_results)

        primary = self.search(query, n_results=n_results, category=category)
        # 결과가 절반 이하면 전체 검색에서 보강
        if len(primary) < max(n_results // 2, 5):
            extra = self.search(query, n_results=n_results)
            seen = {a['id'] for a in primary}
            for a in extra:
                if a['id'] not in seen:
                    primary.append(a)
                    if len(primary) >= n_results:
                        break
        return primary

    def count(self):
        return self.collection.count()
