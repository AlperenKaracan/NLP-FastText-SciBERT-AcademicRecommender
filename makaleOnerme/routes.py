import os
import time
import numpy as np
from datetime import datetime
from collections import Counter
from bson.objectid import ObjectId
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    jsonify, session, flash, current_app
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, TOP_INTERESTS
from utils import (
    longString_to_FastText_Vector, longString_to_sciBERT_Vector,
    remove_duplicates_within_model, filter_out_favorites,
    get_top_similar_articles, compute_precision_recall, allowed_file, is_relevant, get_article_id
)
from pymongo import MongoClient

bp = Blueprint('main', __name__)
client = MongoClient("mongodb://localhost:27017")
db = client["makaleOner"]
article_collection = db["article_db"]
user_collection = db["user_db"]
comment_collection = db["comment_db"]

article_collection.create_index("document_string")
article_collection.create_index("document_title")
article_collection.create_index("extractive_keyphrases")

@bp.context_processor
def utility_processor():
    return dict(get_article_id=get_article_id)


@bp.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("main.user_page", user_ID=session["user_id"]))
    return render_template("login.html", dynamic_interests=TOP_INTERESTS)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        interests = request.form.getlist("interests")

        if user_collection.find_one({"username": username}):
            flash("Bu kullanıcı adı zaten var!")
            return redirect(url_for("main.register"))

        hashed_pw = generate_password_hash(password)
        new_id = 0
        while user_collection.find_one({"user_ID": new_id}):
            new_id += 1

        user_data = {
            "user_ID": new_id,
            "username": username,
            "password": hashed_pw,
            "user_history": len(interests),
            "interests": interests,
            "user_interests_FastText_vector": longString_to_FastText_Vector(" ".join(interests), current_app.config[
                "MODEL_FASTTEXT"]).tolist(),
            "user_interests_sciBERT_vector": longString_to_sciBERT_Vector(" ".join(interests),
                                                                          current_app.config["TOKENIZER"],
                                                                          current_app.config["MODEL_BERT"]).tolist(),
            "favorites": []
        }
        user_collection.insert_one(user_data)
        session["user_id"] = new_id
        session["username"] = username
        flash("Kayıt başarılı! Hoşgeldiniz.")
        return redirect(url_for("main.user_page", user_ID=new_id))
    else:
        return render_template("login.html", dynamic_interests=TOP_INTERESTS)


@bp.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    user = user_collection.find_one({"username": username})
    if user and check_password_hash(user["password"], password):
        session["user_id"] = user["user_ID"]
        session["username"] = user["username"]
        flash("Giriş başarılı.")
        return redirect(url_for("main.user_page", user_ID=user["user_ID"]))
    flash("Giriş başarısız, tekrar deneyin.")
    return redirect(url_for("main.index"))


@bp.route("/logout")
def logout():
    session.clear()
    flash("Çıkış yapıldı.")
    return redirect(url_for("main.index"))


@bp.route("/profile/<int:user_ID>", methods=["GET", "POST"])
def profile(user_ID):
    user_data = user_collection.find_one({"user_ID": user_ID})
    if not user_data:
        flash("Kullanıcı bulunamadı.")
        return redirect(url_for("main.index"))
    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        new_interests = request.form.getlist("interests")
        if new_password.strip():
            hashed_pw = generate_password_hash(new_password)
            user_collection.update_one({"user_ID": user_ID}, {"$set": {"password": hashed_pw}})
        if new_interests:
            user_history = len(new_interests)
            txt_int = " ".join(new_interests)
            ft_model = current_app.config["MODEL_FASTTEXT"]
            tokenizer = current_app.config["TOKENIZER"]
            model_BERT = current_app.config["MODEL_BERT"]
            ft_vec = longString_to_FastText_Vector(txt_int, ft_model)
            sb_vec = longString_to_sciBERT_Vector(txt_int, tokenizer, model_BERT)
            user_collection.update_one(
                {"user_ID": user_ID},
                {"$set": {
                    "interests": new_interests,
                    "user_interests_FastText_vector": ft_vec.tolist(),
                    "user_interests_sciBERT_vector": sb_vec.tolist(),
                    "user_history": user_history
                }}
            )
        flash("Profil güncellendi.")
        return redirect(url_for("main.profile", user_ID=user_ID))
    else:
        return render_template("profile.html", user_data=user_data, dynamic_interests=TOP_INTERESTS)


@bp.route("/user/<int:user_ID>")
def user_page(user_ID):
    user_data = user_collection.find_one({"user_ID": user_ID})
    if not user_data:
        flash("Kullanıcı bulunamadı.")
        return redirect(url_for("main.index"))

    ft_vec = np.array(user_data.get("user_interests_FastText_vector", []))
    sb_vec = np.array(user_data.get("user_interests_sciBERT_vector", []))

    top_fasttext = get_top_similar_articles(
        ft_vec,
        article_collection.find(
            {},
            {
                "document_string": 1,
                "document_ID": 1,
                "extractive_keyphrases": 1,
                "document_FastText_vector": 1,
                "document_sciBERT_vector": 1,
                "abstract": 1,
                "doc_bio_tags": 1,
                "abstractive_keyphrases": 1
            }
        ).limit(50),
        "document_FastText_vector", count=30
    )

    top_scibert = get_top_similar_articles(
        sb_vec,
        article_collection.find(
            {},
            {
                "document_string": 1,
                "document_ID": 1,
                "extractive_keyphrases": 1,
                "document_sciBERT_vector": 1,
                "document_FastText_vector": 1,
                "abstract": 1,
                "doc_bio_tags": 1,
                "abstractive_keyphrases": 1
            }
        ).limit(50),
        "document_sciBERT_vector", count=30
    )

    top_fasttext = remove_duplicates_within_model(top_fasttext)
    top_scibert = remove_duplicates_within_model(top_scibert)

    fav_list = set(user_data.get("favorites", []))
    def filter_articles(articles):
        filtered = []
        for art, sim in articles:
            art_id = get_article_id(art)
            if art_id not in fav_list:
                filtered.append((art, sim))
        return filtered

    top_fasttext = filter_articles(top_fasttext)
    top_scibert = filter_articles(top_scibert)

    top_fasttext = top_fasttext[:5]
    top_scibert = top_scibert[:5]

    user_ints = user_data.get("interests", [])
    all_articles = list(article_collection.find({}, {"document_string": 1, "extractive_keyphrases": 1}))
    fasttext_precision, fasttext_recall = compute_precision_recall(top_fasttext, user_ints, all_articles)
    scibert_precision, scibert_recall = compute_precision_recall(top_scibert, user_ints, all_articles)

    return render_template("userpage.html",
                           user_data_var=user_data,
                           fasttext_articles=top_fasttext,
                           scibert_articles=top_scibert,
                           fasttext_precision=fasttext_precision,
                           fasttext_recall=fasttext_recall,
                           scibert_precision=scibert_precision,
                           scibert_recall=scibert_recall)


@bp.route("/user/<int:user_ID>/remove_favorite/<article_ID>", endpoint="remove_favorite")
def remove_favorite(user_ID, article_ID):
    user_data = user_collection.find_one({"user_ID": user_ID})
    if not user_data:
        flash("Kullanıcı bulunamadı.")
        return redirect(url_for("main.index"))
    stored_favs = [str(fid) for fid in user_data.get("favorites", [])]
    if article_ID in stored_favs:
        user_collection.update_one({"user_ID": user_ID}, {"$pull": {"favorites": article_ID}})
        flash("Makale favorilerden çıkarıldı.")
    else:
        flash("Bu makale favorilerinizde yok!")
    return redirect(url_for("main.user_page", user_ID=user_ID))



@bp.route("/favorites/<int:user_ID>")
def favorites(user_ID):
    from bson.objectid import ObjectId
    user_data = user_collection.find_one({"user_ID": user_ID})
    if not user_data:
        flash("Kullanıcı bulunamadı.")
        return redirect(url_for("main.index"))
    fav_ids = user_data.get("favorites", [])
    fav_list = []
    for fid in fav_ids:
        art = article_collection.find_one({"document_ID": fid})
        if not art:
            try:
                art = article_collection.find_one({"_id": ObjectId(fid)})
            except Exception:
                art = None
        if art:
            fav_list.append(art)
    counter = Counter()
    for art in fav_list:
        for kp in art.get("extractive_keyphrases", []):
            counter.update([kp])
    fav_stats = [{"key": kp, "count": cnt} for kp, cnt in counter.most_common(5)]
    return render_template("favorites.html", favorites=fav_list, fav_stats=fav_stats)



@bp.route("/search-suggestions", methods=["GET"])
def search_suggestions():
    q = request.args.get("q", "").lower()
    suggestions = []
    if q:
        cur = article_collection.find({"document_title": {"$regex": q, "$options": "i"}}, {"document_title": 1}).limit(
            10)
        for art in cur:
            title = art.get("document_title", f"Makale {get_article_id(art)}")
            suggestions.append(title)
    return jsonify({"suggestions": suggestions})


@bp.route("/filter-suggestions", methods=["GET"])
def filter_suggestions():
    f = request.args.get("f", "").lower()
    suggestions = []
    if f:
        cur = article_collection.find({"document_string": {"$regex": f, "$options": "i"}},
                                      {"document_string": 1}).limit(10)
        for doc in cur:
            excerpt = doc.get("document_string", "")
            did = get_article_id(doc)
            suggestions.append(f"ID:{did} => {excerpt[:60]}...")
    return jsonify({"suggestions": suggestions})


@bp.route("/interest-suggestions", methods=["GET"])
def interest_suggestions():
    i = request.args.get("q", "").lower()
    suggestions = []
    if i:
        cur = article_collection.find({"extractive_keyphrases": {"$regex": i, "$options": "i"}},
                                      {"extractive_keyphrases": 1}).limit(10)
        found = set()
        for doc in cur:
            for kp in doc.get("extractive_keyphrases", []):
                if i in kp.lower():
                    found.add(kp)
        suggestions = list(found)
    return jsonify({"suggestions": suggestions})


@bp.route("/user/search/<int:user_ID>", methods=["POST"])
def user_search(user_ID):
    user_data = user_collection.find_one({"user_ID": user_ID})
    if not user_data:
        flash("Kullanıcı bulunamadı.")
        return redirect(url_for("main.index"))
    search_query = request.form.get("search_query", "")
    if not search_query:
        return redirect(url_for("main.user_page", user_ID=user_ID))
    ft_model = current_app.config["MODEL_FASTTEXT"]
    tokenizer = current_app.config["TOKENIZER"]
    model_BERT = current_app.config["MODEL_BERT"]
    ft_vec = longString_to_FastText_Vector(search_query, ft_model)
    sb_vec = longString_to_sciBERT_Vector(search_query, tokenizer, model_BERT)
    big_count = 30
    top_ft = get_top_similar_articles(
        ft_vec,
        article_collection.find({}, {"document_string": 1, "extractive_keyphrases": 1, "document_FastText_vector": 1,
                                     "document_sciBERT_vector": 1, "abstract": 1}),
        "document_FastText_vector", big_count)
    top_sb = get_top_similar_articles(
        sb_vec,
        article_collection.find({}, {"document_string": 1, "extractive_keyphrases": 1, "document_sciBERT_vector": 1,
                                     "document_FastText_vector": 1, "abstract": 1}),
        "document_sciBERT_vector", big_count)
    top_ft = remove_duplicates_within_model(top_ft)
    top_sb = remove_duplicates_within_model(top_sb)
    fav_list = user_data.get("favorites", [])
    top_ft = filter_out_favorites(top_ft, fav_list)
    top_sb = filter_out_favorites(top_sb, fav_list)
    top_ft = top_ft[:5]
    top_sb = top_sb[:5]
    all_articles = list(article_collection.find({}, {"document_string": 1, "extractive_keyphrases": 1}))
    user_ints = user_data.get("interests", [])
    ft_precision, ft_recall = compute_precision_recall(top_ft, user_ints, all_articles)
    sb_precision, sb_recall = compute_precision_recall(top_sb, user_ints, all_articles)
    return render_template("userpage.html",
                           user_data_var=user_data,
                           fasttext_articles=top_ft,
                           scibert_articles=top_sb,
                           fasttext_precision=ft_precision,
                           fasttext_recall=ft_recall,
                           scibert_precision=sb_precision,
                           scibert_recall=sb_recall)


@bp.route("/user/filter/<int:user_ID>", methods=["POST"])
def user_filter(user_ID):
    user_data = user_collection.find_one({"user_ID": user_ID})
    if not user_data:
        flash("Kullanıcı bulunamadı.")
        return redirect(url_for("main.index"))
    filter_query = request.form.get("filter_query", "")
    if not filter_query:
        return redirect(url_for("main.user_page", user_ID=user_ID))
    results = []
    for article in article_collection.find({}, {"document_string": 1, "extractive_keyphrases": 1}):
        if filter_query.lower() in article.get("document_string", "").lower():
            results.append((article, 0.0))
    results = remove_duplicates_within_model(results)
    fav_list = user_data.get("favorites", [])
    results = filter_out_favorites(results, fav_list)
    half = len(results) // 2
    left_list = results[:half]
    right_list = results[half:]
    all_articles = list(article_collection.find({}, {"document_string": 1, "extractive_keyphrases": 1}))
    user_ints = user_data.get("interests", [])
    left_precision, left_recall = compute_precision_recall(left_list, user_ints, all_articles)
    right_precision, right_recall = compute_precision_recall(right_list, user_ints, all_articles)
    return render_template("userpage.html",
                           user_data_var=user_data,
                           fasttext_articles=left_list,
                           scibert_articles=right_list,
                           fasttext_precision=left_precision,
                           fasttext_recall=left_recall,
                           scibert_precision=right_precision,
                           scibert_recall=right_recall)


@bp.route("/user/interest/<int:user_ID>", methods=["POST"])
def user_interest_filter(user_ID):
    user_data = user_collection.find_one({"user_ID": user_ID})
    if not user_data:
        flash("Kullanıcı bulunamadı.")
        return redirect(url_for("main.index"))
    interest_query = request.form.get("interest_query", "")
    if not interest_query:
        return redirect(url_for("main.user_page", user_ID=user_ID))
    results = []
    for article in article_collection.find({}, {"extractive_keyphrases": 1}):
        if interest_query in article.get("extractive_keyphrases", []):
            results.append((article, 0.0))
    results = remove_duplicates_within_model(results)
    fav_list = user_data.get("favorites", [])
    results = filter_out_favorites(results, fav_list)
    half = len(results) // 2
    left_list = results[:half]
    right_list = results[half:]
    all_articles = list(article_collection.find({}, {"document_string": 1, "extractive_keyphrases": 1}))
    user_ints = user_data.get("interests", [])
    left_precision, left_recall = compute_precision_recall(left_list, user_ints, all_articles)
    right_precision, right_recall = compute_precision_recall(right_list, user_ints, all_articles)
    return render_template("userpage.html",
                           user_data_var=user_data,
                           fasttext_articles=left_list,
                           scibert_articles=right_list,
                           fasttext_precision=left_precision,
                           fasttext_recall=left_recall,
                           scibert_precision=right_precision,
                           scibert_recall=right_recall)


@bp.route("/articlepage/<article_ID>")
def article_page(article_ID):
    from bson.objectid import ObjectId
    article_data = article_collection.find_one({"document_ID": article_ID})
    if not article_data:
        try:
            article_data = article_collection.find_one({"_id": ObjectId(article_ID)})
        except Exception:
            article_data = None
    if not article_data:
        flash("Makale bulunamadı.")
        return redirect(url_for("main.user_page", user_ID=session.get("user_id")))
    comments = list(comment_collection.find({"article_id": article_ID}).sort("timestamp", 1))
    return render_template("article.html", article_data=article_data, comments=comments)


@bp.route("/add_comment", methods=["POST"])
def add_comment():
    article_id = request.form.get("article_id")
    ctext = request.form.get("comment", "")
    uname = session.get("username", "Anonim")
    comment_data = {
        "article_id": article_id,
        "comment": ctext,
        "username": uname,
        "timestamp": datetime.utcnow()
    }
    comment_collection.insert_one(comment_data)
    flash("Yorum eklendi.")
    return redirect(url_for("main.article_page", article_ID=article_id))


@bp.route("/user/<int:user_ID>/article/<article_ID>")
def article_liked(user_ID, article_ID):
    from bson.objectid import ObjectId
    user_data = user_collection.find_one({"user_ID": user_ID})
    article_data = article_collection.find_one({"document_ID": article_ID})
    if not article_data:
        try:
            article_data = article_collection.find_one({"_id": ObjectId(article_ID)})
        except Exception:
            article_data = None
    if not user_data or not article_data:
        flash("Kullanıcı veya makale bulunamadı.")
        return redirect(url_for("main.user_page", user_ID=user_ID))

    full_article_id = get_article_id(article_data)

    for kp in article_data.get("extractive_keyphrases", []):
        if kp not in user_data.get("interests", []):
            user_collection.update_one({"user_ID": user_ID}, {"$push": {"interests": kp}})

    if full_article_id not in user_data.get("favorites", []):
        user_collection.update_one({"user_ID": user_ID}, {"$push": {"favorites": full_article_id}})

    # Kullanıcının embedding'lerini güncelle (ağırlıklı ortalama yöntemiyle)
    history = user_data.get("user_history", 0)
    old_ft = np.array(user_data.get("user_interests_FastText_vector", []))
    old_sb = np.array(user_data.get("user_interests_sciBERT_vector", []))
    article_ft = np.array(article_data.get("document_FastText_vector", []))
    article_sb = np.array(article_data.get("document_sciBERT_vector", []))
    new_ft = (old_ft * history + article_ft) / (history + 1) if history > 0 else article_ft
    new_sb = (old_sb * history + article_sb) / (history + 1) if history > 0 else article_sb

    user_collection.update_one(
        {"user_ID": user_ID},
        {"$set": {
            "user_interests_FastText_vector": new_ft.tolist(),
            "user_interests_sciBERT_vector": new_sb.tolist()
        },
            "$inc": {"user_history": 1}}
    )

    flash("Makale favorilere eklendi.")
    return redirect(url_for("main.user_page", user_ID=user_ID))
