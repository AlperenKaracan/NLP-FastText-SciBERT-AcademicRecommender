import os
import time
from flask import Flask
from config import SECRET_KEY, DEBUG, UPLOAD_FOLDER, TOP_INTERESTS, FASTTEXT_MODEL_PATH, SCIBERT_MODEL_NAME
from routes import bp as main_bp
import fasttext
from transformers import BertModel, BertTokenizer

def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["DEBUG"] = DEBUG
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["TOP_INTERESTS"] = TOP_INTERESTS

    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        print("Modeller yükleniyor...")
        start = time.time()
        ft_model = fasttext.load_model(FASTTEXT_MODEL_PATH)
        load_time = time.time() - start
        print(f"FastText modeli {load_time:.2f} saniyede yüklendi.")
        tokenizer = BertTokenizer.from_pretrained(SCIBERT_MODEL_NAME)
        model_BERT = BertModel.from_pretrained(SCIBERT_MODEL_NAME)
        print("SciBERT modeli yüklendi.")
        app.config["MODEL_FASTTEXT"] = ft_model
        app.config["TOKENIZER"] = tokenizer
        app.config["MODEL_BERT"] = model_BERT
    else:
        print("Reloader: Model yüklemesi atlanıyor.")

    app.register_blueprint(main_bp)
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='127.0.0.1', port=5000, debug=DEBUG)
