# coding=utf-8
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import pytest
import logging

from rasa_nlu.evaluate import is_token_within_entity, do_entities_overlap, merge_labels, patch_duckling_entities, \
    remove_empty_intent_examples, get_entity_extractors, get_duckling_dimensions, known_duckling_dimensions, \
    find_component, patch_duckling_extractors
from rasa_nlu.evaluate import does_token_cross_borders
from rasa_nlu.evaluate import align_entity_predictions
from rasa_nlu.evaluate import determine_intersection
from rasa_nlu.tokenizers import Token
from tests import utilities

logging.basicConfig(level="DEBUG")


@pytest.fixture(scope="module")
def duckling_interpreter(component_builder):
    _conf = utilities.base_test_conf("")
    _conf["pipeline"] = ["ner_duckling"]
    _conf["data"] = "./data/examples/rasa/demo-rasa.json"
    return utilities.interpreter_for(component_builder, _conf)


# Chinese Example
# "对面食过敏" -> To be allergic to wheat-based food
CH_wrong_segmentation = [Token("对面", 0), Token("食", 2), Token("过敏", 3)]  # opposite, food, allergy
CH_correct_segmentation = [Token("对", 0), Token("面食", 1), Token("过敏", 3)]  # towards, wheat-based food, allergy
CH_wrong_entity = {
    "start": 0,
    "end": 2,
    "value": "对面",
    "entity": "direction"

}
CH_correct_entity = {
    "start": 1,
    "end": 3,
    "value": "面食",
    "entity": "food_type"
}

# EN example
# "Hey Robot, I would like to eat pizza near Alexanderplatz tonight"
EN_indices = [0, 4, 9, 11, 13, 19, 24, 27, 31, 37, 42, 57]
EN_tokens = ["Hey", "Robot", ",", "I", "would", "like", "to", "eat", "pizza", "near", "Alexanderplatz", "tonight"]
EN_tokens = [Token(t, i) for t, i in zip(EN_tokens, EN_indices)]

EN_targets = [
    {
        "start": 31,
        "end": 36,
        "value": "pizza",
        "entity": "food"
    },
    {
        "start": 37,
        "end": 56,
        "value": "near Alexanderplatz",
        "entity": "location"
    },
    {
        "start": 57,
        "end": 64,
        "value": "tonight",
        "entity": "datetime"
    }
]

EN_predicted = [
    {
        "start": 4,
        "end": 9,
        "value": "Robot",
        "entity": "person",
        "extractor": "A"
    },
    {
        "start": 31,
        "end": 36,
        "value": "pizza",
        "entity": "food",
        "extractor": "A"
    },
    {
        "start": 42,
        "end": 56,
        "value": "Alexanderplatz",
        "entity": "location",
        "extractor": "A"
    },
    {
        "start": 42,
        "end": 64,
        "value": "Alexanderplatz tonight",
        "entity": "movie",
        "extractor": "B"
    }
]


def test_token_entity_intersection():
    # included
    assert determine_intersection(CH_correct_segmentation[1], CH_correct_entity) == len(CH_correct_segmentation[1].text)

    # completely outside
    assert determine_intersection(CH_correct_segmentation[2], CH_correct_entity) == 0

    # border crossing
    assert determine_intersection(CH_correct_segmentation[1], CH_wrong_entity) == 1


def test_token_entity_boundaries():
    # smaller and included
    assert is_token_within_entity(CH_wrong_segmentation[1], CH_correct_entity) == True
    assert does_token_cross_borders(CH_wrong_segmentation[1], CH_correct_entity) == False

    # exact match
    assert is_token_within_entity(CH_correct_segmentation[1], CH_correct_entity) == True
    assert does_token_cross_borders(CH_correct_segmentation[1], CH_correct_entity) == False

    # completely outside
    assert is_token_within_entity(CH_correct_segmentation[0], CH_correct_entity) == False
    assert does_token_cross_borders(CH_correct_segmentation[0], CH_correct_entity) == False

    # border crossing
    assert is_token_within_entity(CH_wrong_segmentation[0], CH_correct_entity) == False
    assert does_token_cross_borders(CH_wrong_segmentation[0], CH_correct_entity) == True


def test_entity_overlap():
    assert do_entities_overlap([CH_correct_entity, CH_wrong_entity]) == True
    assert do_entities_overlap(EN_targets) == False


def test_label_merging():
    aligned_predictions = [
        {"target_labels": ["O", "O"], "extractor_labels": {"A": ["O", "O"]}},
        {"target_labels": ["LOC", "O", "O"], "extractor_labels": {"A": ["O", "O", "O"]}}
    ]

    assert all(merge_labels(aligned_predictions) == ["O", "O", "LOC", "O", "O"])
    assert all(merge_labels(aligned_predictions, "A") == ["O", "O", "O", "O", "O"])


def test_duckling_patching():
    entities = [[
        {
            "start": 37,
            "end": 56,
            "value": "near Alexanderplatz",
            "entity": "location",
            "extractor": "ner_crf"
        },
        {
            "start": 57,
            "end": 64,
            "value": "tonight",
            "entity": "Time",
            "extractor": "ner_duckling"

        }
    ]]
    patched = [[
        {
            "start": 37,
            "end": 56,
            "value": "near Alexanderplatz",
            "entity": "location",
            "extractor": "ner_crf"
        },
        {
            "start": 57,
            "end": 64,
            "value": "tonight",
            "entity": "Time",
            "extractor": "ner_duckling (Time)"

        }
    ]]
    assert patch_duckling_entities(entities) == patched


def test_empty_intent_removal():
    targets = ["", "greet"]
    predicted = ["restaurant_search", "greet"]

    targets_r, predicted_r = remove_empty_intent_examples(targets, predicted)

    assert targets_r == ["greet"]
    assert predicted_r == ["greet"]


def test_evaluate_entities():
    mock_extractors = ["A", "B"]
    result = align_entity_predictions(EN_targets, EN_predicted, EN_tokens, mock_extractors)
    assert result == {
        "target_labels": ["O", "O", "O", "O", "O", "O", "O", "O", "food", "location", "location", "datetime"],
        "extractor_labels": {
            "A": ["O", "person", "O", "O", "O", "O", "O", "O", "food", "O", "location", "O"],
            "B": ["O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "movie", "movie"]
        }
    }, "Wrong entity prediction alignment"


def test_get_entity_extractors(duckling_interpreter):
    assert get_entity_extractors(duckling_interpreter) == {"ner_duckling"}


def test_get_duckling_dimensions(duckling_interpreter):
    assert set(get_duckling_dimensions(duckling_interpreter, "ner_duckling")) == known_duckling_dimensions


def test_find_component(duckling_interpreter):
    assert find_component(duckling_interpreter, "ner_duckling").name == "ner_duckling"


def test_patch_duckling_extractors(duckling_interpreter):
    target = {"ner_duckling ({})".format(dim) for dim in known_duckling_dimensions}
    patched = patch_duckling_extractors(duckling_interpreter, {"ner_duckling"})
    assert patched == target
