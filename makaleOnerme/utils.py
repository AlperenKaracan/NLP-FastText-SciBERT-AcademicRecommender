import os
import time
import string
import numpy as np
import torch
import fasttext
import nltk
from difflib import SequenceMatcher
from collections import Counter
from datetime import datetime
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords as nltk_stopwords
from nltk.stem import PorterStemmer
from sklearn.metrics.pairwise import cosine_similarity
from pymongo import MongoClient


nltk.download("stopwords")
nltk.download("punkt")
stop_words = set(nltk_stopwords.words("english"))
stemmer = PorterStemmer()


def preprocess_text(text: str) -> str:
    """Metni normalize eder: küçük harfe çevirme, noktalama temizleme, stop word kaldırma, kök bulma."""
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    tokens = word_tokenize(text)
    tokens = [t for t in tokens if t not in stop_words]
    tokens = [stemmer.stem(t) for t in tokens]
    return " ".join(tokens)


def longString_to_FastText_Vector(text: str, model_fasttext) -> np.ndarray:
    processed = preprocess_text(text)
    tokens = processed.split()
    if not tokens:
        return np.zeros((300,))
    vectors = [model_fasttext.get_word_vector(tok) for tok in tokens]
    return np.mean(vectors, axis=0)


def longString_to_sciBERT_Vector(text: str, tokenizer, model_Bert) -> np.ndarray:
    processed = preprocess_text(text)
    inputs = tokenizer(processed, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        outputs = model_Bert(**inputs)
    embeddings = outputs.last_hidden_state
    avg_emb = torch.mean(embeddings, dim=1)
    return avg_emb.squeeze().cpu().numpy()


def get_cosine_similarity(v1, v2) -> float:
    v1 = np.array(v1).reshape(1, -1)
    v2 = np.array(v2).reshape(1, -1)
    return cosine_similarity(v1, v2)[0][0]


def allowed_file(filename: str, allowed_extensions: set) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


def get_article_id(article) -> str:
    doc_id = article.get("document_ID")
    if doc_id is not None:
        doc_id_str = str(doc_id)
        if len(doc_id_str) >= 24:
            return doc_id_str
    return str(article.get("_id"))

def remove_duplicates_within_model(articles: list) -> list:
    seen_ids = set()
    filtered = []
    for art, sim in articles:
        doc_id = get_article_id(art)
        if doc_id not in seen_ids:
            filtered.append((art, sim))
            seen_ids.add(doc_id)
    return filtered


def filter_out_favorites(articles: list, favorites: list) -> list:
    fav_set = set(favorites)
    filtered = []
    for art, sim in articles:
        doc_id = get_article_id(art)
        if doc_id not in fav_set:
            filtered.append((art, sim))
    return filtered


def get_top_similar_articles(vector, articles_cursor, vector_field: str, count: int = 30) -> list:
    sims = []
    for article in articles_cursor:
        dvec = article.get(vector_field, [])
        if not dvec:
            continue
        sim = get_cosine_similarity(vector, dvec)
        sims.append((article, sim))
    sims.sort(key=lambda x: x[1], reverse=True)
    return sims[:count]


from difflib import SequenceMatcher


def similarity_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def is_relevant(article, user_interests):
    """
    Kullanıcı ilgi alanları ile makale içeriği arasındaki benzerliği kontrol eder.
    Eğer makalede extractive_keyphrases varsa, bunlarla karşılaştırılır;
    aksi halde, document_string içeriği üzerinden kontrol edilir.
    Benzerlik eşiği %60 olarak ayarlanmıştır.
    """
    normalized_interests = [interest.lower() for interest in user_interests]

    keyphrases = article.get("extractive_keyphrases", [])
    if keyphrases:
        normalized_kps = [kp.lower() for kp in keyphrases]
        for interest in normalized_interests:
            if interest in normalized_kps:
                return True
        for interest in normalized_interests:
            for kp in normalized_kps:
                if similarity_ratio(interest, kp) >= 0.6:
                    return True
        return False
    else:
        doc = article.get("document_string", "")
        processed_doc = preprocess_text(doc)
        tokens = processed_doc.split()
        for interest in normalized_interests:
            if interest in tokens:
                return True
        for interest in normalized_interests:
            for token in tokens:
                if similarity_ratio(interest, token) >= 0.6:
                    return True
        return False


def compute_precision_recall(articles: list, user_interests: list, all_articles: list) -> (float, float):
    if not articles:
        return 0.0, 0.0
    TP = sum(1 for art, sim in articles if is_relevant(art, user_interests))
    all_relevant = sum(1 for art in all_articles if is_relevant(art, user_interests))
    precision = round(TP / len(articles), 3) if articles else 0.0
    recall = round(TP / all_relevant, 3) if all_relevant > 0 else 0.0
    return precision, recall
