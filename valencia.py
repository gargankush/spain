"""
Script to make real-time predictions.
"""

import os
import re
import sys

import logging

import requests
import pickle
import html2text

from slugify import slugify

from keras.datasets import reuters
from keras.models import model_from_json

import nltk
import spacy
from nltk.tag.stanford import StanfordNERTagger

# Initializing constants.
LOG_LEVEL = logging.INFO
MODEL_PATH = os.path.join("models", "{}_model.json")
WEIGHTS_PATH = os.path.join("models", "{}_weights.h5")
TOKENIZER_PATH = os.path.join("models", "{}_tokenizer.pkl")
BINARY = "binary"
TOP_CLASSES = 40
HTML_PATH = os.path.join("html")
PREDICTIONS_PATH = os.path.join("predictions")
URLS_PATH = os.path.join("urls.csv")
MADRID_PATH = os.path.join("madrid.txt")
TEXT_TRUNCATE = (0.1, 0.7)
STF_JAR = './stanford-ner/stanford-ner.jar'
STF_GZ = './stanford-ner/classifiers/english.all.3class.distsim.crf.ser.gz'

# Loading labels.
LABELS = [
    'cocoa','grain','veg-oil','earn','acq','wheat','copper','housing','money-supply',
    'coffee','sugar','trade','reserves','ship','cotton','carcass','crude','nat-gas',
    'cpi','money-fx','interest','gnp','meal-feed','alum','oilseed','gold','tin',
    'strategic-metal','livestock','retail','ipi','iron-steel','rubber','heat','jobs',
    'lei','bop','zinc','orange','pet-chem','dlr','gas','silver','wpi','hog','lead',
]

# Initializing SpaCy.
nlp = spacy.load("en_core_web_sm")

# Initializing logger.
logger = logging.getLogger(__name__)
# handler = logging.StreamHandler(sys.stdout)
# handler.setLevel(logging.DEBUG)
# formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s - %(message)s')
# handler.setFormatter(formatter)
# logger.addHandler(handler)
logger.setLevel(LOG_LEVEL)

# Define functio nto slugify strings.
def normalize(my_string: str):
    return "".join(
        x for x in slugify(my_string)
        if x.isalnum
        and x not in ("-", ".")
    )

# Loading script version.
version = sys.argv[1] if len(sys.argv) > 1 else ""
if not version:
    raise ValueError("Model version is required.")
logger.debug("Version initilized. | sf_value=%s", version)

# Detecting model path.
model_path = MODEL_PATH.format(version)
if not os.path.isfile(model_path):
    raise OSError("File not found:", model_path)
logger.debug("Model path found. | sf_path=%s", model_path)

# Detecting weights path.
weights_path = WEIGHTS_PATH.format(version)
if not os.path.isfile(weights_path):
    raise OSError("Weights not found:", weights_path)
logger.debug("Weights path found. | sf_path=%s", weights_path)

# Loading prediction model from file.
# load json and create model
with open(model_path, 'r') as file_buffer:
    loaded_model_json = file_buffer.read()
model = model_from_json(loaded_model_json)
model.load_weights(weights_path)
logger.debug("Prediction model loaded. | sf_model=%s", model)

# Loading the Tokenizer.
tokenizer_path = TOKENIZER_PATH.format(version)
if not os.path.isfile(tokenizer_path):
    raise OSError("File not found:", tokenizer_path)
with open(tokenizer_path, 'rb') as file_buffer:
    tokenizer = pickle.load(file_buffer)
logger.debug("Tokenizer loaded. | sf_tokenizer=%s", tokenizer)

# Loading the words index.
word_index = reuters.get_word_index()
logger.debug("Word index loaded. | sf_index=%s", len(word_index))
# Indexing all labels in the dataset.
id_by_word_index = {}
for key, value in word_index.items():
    id_by_word_index[key] = value
logger.debug("Indexed words by ID. | sf_index=%s", len(id_by_word_index))

# Initializing HTML processor.
html_processor = html2text.HTML2Text()

# Initializing madrid report.
madrid = {}
if os.path.isfile(MADRID_PATH):
    with open(MADRID_PATH, "r") as file_buffer:
        for line in file_buffer.read().split("\n"):
            if line:
                label, score = line.split()
                madrid[label] = float(score)
logger.debug("Madrid report loaded. | sf_madrid=%s", madrid)

# Reading URL or all.
if len(sys.argv) > 2:
    batch = False
    urls = sys.argv[2:]
else:

    # Reading URLs from file.
    batch = True
    logger.debug("Reading URLs from File. | sf_path=%s", URLS_PATH)
    with open(URLS_PATH, "r") as file_buffer:
        urls = (
            line.split(",")[0]
            for line in file_buffer.read().split("\n")
            if line.startswith("http")
        )
    logger.debug("URLs obtained from file. | sf_path=%s", URLS_PATH)

# Parsing each URL individually.
for url in urls:
    logger.info("Parsing URL. | sf_url=%s", url)

    # Checking if URL is loca 
    cache_path = os.path.join(HTML_PATH, normalize(url))
    if os.path.isfile(cache_path):

        # Loading file from the local file system.
        logger.debug("Loading local content. | sf_url=%s", url)
        with open(cache_path, "r") as file_buffer:
            text = file_buffer.read()
        logger.debug("Local content loaded. | sf_url=%s", url)

    else:

        # Loading URL content.
        logger.debug("Downloading content. | sf_url=%s", url)
        response = requests.get(url)
        logger.debug("Respose obtained. | sf_response=%s", response)
        if response.status_code != 200:
            logger.error("Error detected. | sf_response=%s", response)
            raise RuntimeError("Bad request:", url)
        logger.debug("Downloaded content. | sf_url=%s", url)
        text = response.text

        # SAving to cache.
        with open(cache_path, "w") as file_buffer:
            file_buffer.write(text)
        logger.debug("Cache saved. | sf_url=%s", cache_path)

    # Remove head and footer.
    text = re.sub(r".*<body>", "", text)
    text = re.sub(r"</body>.*", "", text)
    logger.debug("Body extracted. | sf_text=%s", len(text))

    # POS tagging with NLTK.
    nltk_entities = [
        (chunk.label(), ' '.join(c[0] for c in chunk))
        for sent in nltk.sent_tokenize(text)
        for chunk in nltk.ne_chunk(nltk.pos_tag(nltk.word_tokenize(sent)))
        if hasattr(chunk, 'label')
    ]
    nltk_people = [
        entity[1]
        for entity in nltk_entities
        if entity[0] == 'PERSON'
    ]
    nltk_organizations = [
        entity[1]
        for entity in nltk_entities
        if entity[0] == 'ORGANIZATION'
    ]
    nltk_locations = [
        entity[1]
        for entity in nltk_entities
        if entity[0] == 'GPE'
    ]
    logger.debug("NLTK NER. | sf_people=%s", nltk_people)
    logger.debug("NLTK NER. | sf_location=%s", nltk_locations)
    logger.debug("NLTK NER. | sf_organization=%s", nltk_organizations)

    # POS tagging with Stanford NER tagger.
    ner_tagger = StanfordNERTagger(STF_GZ, STF_JAR, encoding='utf8')
    words = nltk.word_tokenize(text)
    stf_people = [tag[0] for tag in ner_tagger.tag(words) if tag[1] == "PERSON"]
    logger.debug("Stanford NER. | sf_people=%s", stf_people)

    # Converting HTML to text.
    text = html_processor.handle(text).lower()
    logger.debug("Extracted raw text. | sf_text=%s", len(text))

    # Analyzing text with SpaCy.
    doc = nlp(text)
    spacy_nouns = [chunk.text for chunk in doc.noun_chunks]
    spacy_verbs = [token.lemma_ for token in doc if token.pos_ == "VERB"]
    spacy_people = [token.lemma_ for token in doc if token.pos_ == "PEOPLE"]
    logger.debug("SpaCy | sf_nouns=%s", spacy_nouns)
    logger.debug("SpaCy | sf_verbs=%s", spacy_verbs)
    logger.debug("SpaCy | sf_people=%s", spacy_people)

    # Truncating text.
    text_array = text.split()
    text_ini = int(len(text_array) * TEXT_TRUNCATE[0])
    text_end = int(len(text_array) * TEXT_TRUNCATE[1])
    text_array = text_array[text_ini:text_end]
    new_text = " ".join(x for x in text_array)
    logger.debug("Text truncated. | sf_text=%s | sf_new=%s", len(text), len(new_text))

    # Tokenizing text.
    x_new = [[
        id_by_word_index[w]
        for w in text.split(" ")
        if w in id_by_word_index
    ]]
    logger.debug("Text indexed. | sf_text=%s", len(x_new))
    x_new = tokenizer.sequences_to_matrix(x_new, mode=BINARY)
    logger.debug("Text tokenized. | sf_text=%s", len(x_new))

    # Make predictions.
    results = model.predict(x_new)
    logger.debug("Text classified. | sf_predictions=%s", len(results[0]))

    # Extract classes from results.
    score_by_class = {
        LABELS[i]: r
        for i, r in enumerate(results[0])
    }
    logger.debug("Classes extracted. | sf_classes=%s", len(score_by_class))

    # Sorting classes by score.
    sorted_classes = sorted(score_by_class, key=lambda x: score_by_class[x], reverse=True)
    logger.debug("Classes sorted. | sf_classes=%s", len(sorted_classes))

    # Saving results to the predictions path.
    predictions_path = os.path.join(PREDICTIONS_PATH, normalize(url))
    logger.debug("Savings results. | sf_path=%s", predictions_path)
    file_buffer = sys.stdout
    if batch:
        file_buffer = open(predictions_path, "w")
    try:

        # Getting top classes. Printing report.
        print("[{}]".format(url), file=file_buffer)
        for name in sorted_classes[:TOP_CLASSES]:
            score = score_by_class[name]
            logger.debug("Top class. | sf_class=%s | sf_score=%s", name, score)
            print("- {}: {}".format(name, score), file=file_buffer)

        # Calculating probability of being accepted.
        if madrid:
            score = 0
            for label in madrid.keys() & score_by_class.keys():
                madrid_score = madrid[label]
                valencia_score = score_by_class[label]
                score += madrid_score * valencia_score / 2
            logger.info("Score calculated. | sf_score=%s", score)
            print("[Score] {}".format(score), file=file_buffer)

        # Printing NLP results:
        print("[Stanford People] {}".format(stf_people), file=file_buffer)
        print("[SpaCy Nouns] {}".format(spacy_nouns), file=file_buffer)
        print("[SpaCy Verbs] {}".format(spacy_verbs), file=file_buffer)
        print("[SpaCy People] {}".format(spacy_people), file=file_buffer)
        print("[NLTK People] {}".format(nltk_people), file=file_buffer)
        print("[NLTK Organizations] {}".format(nltk_organizations), file=file_buffer)
        print("[NLTK Locations] {}".format(nltk_locations), file=file_buffer)
    
    finally:
        if batch:
            file_buffer.close()

    # End of URLs
    logger.info("Text classified. | sf_results=%s", predictions_path)
