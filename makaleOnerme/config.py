import os

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "makaleOner"

FASTTEXT_MODEL_PATH = r"D:\cc.en.300.bin"
SCIBERT_MODEL_NAME = "allenai/scibert_scivocab_uncased"

DEBUG = True
SECRET_KEY = " "

UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

TOP_INTERESTS = [
    "internet",
    "women",
    "simulation",
    "optimization",
    "computer science",
    "robustness",
    "artificial intelligence",
    "information systems",
    "stability",
    "reliability",
    "information technology",
    "neural networks",
    "web sites",
    "history",
    "data mining",
    "modeling",
    "nonlinear systems",
    "survey",
    "genetic algorithm",
    "convergence"
]
