# -*- coding: utf-8 -*-
#
#  test_tatoeba.py
#  cjktools
#

from __future__ import unicode_literals

import os
from io import StringIO
import unittest

from functools import partial
from datetime import datetime

from cjktools.resources import tatoeba, auto_format, cjkdata
from cjktools.common import sopen


def get_data_loc(key, suffix='_00', extension='.csv'):
    script_dir = os.path.dirname(os.path.realpath(__file__))
    data_loc = os.path.join(script_dir, 'sample_data/')
    base_names = dict(sentences='sentences',
                      jpn_indices='jpn_indices',
                      links='links',
                      sentences_detailed='sentences_detailed',
                      edict='je_edict')

    fname = base_names[key] + suffix + extension
    return os.path.join(data_loc, fname)


def get_edict():
    if getattr(get_edict, '_cached', None) is not None:
        return get_edict._cached

    with open(get_data_loc('edict', extension='')) as edf:
        edict = auto_format.load_dictionary(edf)

    get_edict._cached = edict

    return edict


class ReaderBaseCase(unittest.TestCase):
    def resource_fpath(self):
        return get_data_loc(self._resource_name)

    def load_file(self, resource=None, **kwargs):
        """
        Loads the file into a TatoebaSentenceReader object.
        """
        if resource is None:
            resource = self.resource_fpath()

        reader = self.ReaderClass(resource, **kwargs)
        
        return reader


class FileObjReaderMixin(object):
    """
    Mixin to run the existing tests using an already opened file object.
    """
    def load_file(self, resource=None, **kwargs):
        if resource is None:
            resource = self.resource_fpath()

        with open(self.resource_fpath(), mode='r') as resource_file:
            resource_file.filename = self.resource_fpath()

            r = super(FileObjReaderMixin, self).load_file(resource_file,
                                                          **kwargs)

            return r


###
# Tatoeba Reader base class test
class TatoebaReaderTest(unittest.TestCase):
    def test_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            tatoeba.TatoebaReader()


###
# Tatoeba Sentence Reader tests
class TatoebaSentenceReaderTest(ReaderBaseCase):
    _resource_name = 'sentences'
    ReaderClass = tatoeba.TatoebaSentenceReader

    def test_basic(self):
        # Test that all the sentence IDs load properly
        sr = self.load_file()

        sent_ids = [
            29390, 36809, 46235, 54432, 62093, 68807, 82526, 93620, 109744,
            112733, 156245, 192227, 199398, 208975, 224758, 231440, 258289,
            290943, 293946, 310087, 321190, 410787, 2031040, 2031042
        ]

        self.assertEqual(sorted(sr.keys()), sent_ids)
        self.assertEqual(sorted(sr.keys()), sorted(sr.sentence_ids))

    def test_language_filter(self):
        sr = self.load_file(languages={'fra', 'pol', 'rus'})

        sent_ids = [6381, 508870, 2172488]

        self.assertEqual(sorted(sr.keys()), sent_ids)

    def test_custom_filter_row(self):
        class TatoebaSentenceSubsetReader(tatoeba.TatoebaSentenceReader):
            def __init__(self, sentences, subset=None, **kwargs):
                self._subset = set(subset)

                super(TatoebaSentenceSubsetReader, self).__init__(
                    sentences, **kwargs)

            def filter_row(self, row):
                return int(row[0]) not in self._subset

        sr = TatoebaSentenceSubsetReader(
            sentences=self.resource_fpath(),
            subset={224758, 6381, 29390},
            languages={'eng', 'jpn'})

        sent_inds = [29390, 224758]

        self.assertEqual(sorted(sr.keys()), sent_inds)

    def test_language(self):
        sr = self.load_file()

        for sent_id in [82526, 93620, 109744, 208975]:
            self.assertEqual(sr.language(sent_id), 'jpn')

        for sent_id in [36809, 293946, 410787, 2031042]:
            self.assertEqual(sr.language(sent_id), 'eng')

    def test_language_error(self):
        sr = self.load_file()

        with self.assertRaises(tatoeba.InvalidIDError):
            sr.language(193)

    def test_sentence(self):
        sr = self.load_file()

        sentence_pairs = [
            (192227, 'ロールプレイングのテレビゲームは時間を食う。'),
            (29390, 'Role-playing video games are time consuming.'),
            (208975, 'その上手な運転手は車の列を縫うように車を走らせた。'),
            (46235, 'The good driver wove his way through the traffic.')
        ]

        for sent_id, sentence in sentence_pairs:
            self.assertEqual(sr[sent_id], sentence)

    def test_sentence_error(self):
        sr = self.load_file()

        with self.assertRaises(tatoeba.InvalidIDError):
            sr.sentence(24)

    def test_details_error(self):
        sr = self.load_file()

        # One that is in the data set
        with self.assertRaises(tatoeba.MissingDataError):
            sr.details(192227)

        # One that's not in the data set
        with self.assertRaises(tatoeba.MissingDataError):
            sr.details(0)

    def test_repr(self):
        sr = self.load_file()

        expected_fmt = "TatoebaSentenceReader(sentences='{}')"
        expected = expected_fmt.format(self.resource_fpath())

        self.assertEqual(repr(sr), expected)


class TatoebaSentenceReaderDetailedTest(TatoebaSentenceReaderTest):
    _resource_name = 'sentences_detailed'

    def test_details(self):
        sr = self.load_file()

        # Note: I modified 410787 in the csv to make the added/modified
        # different.
        details_pairs = [
            (82526, (None, None, None)),
            (199398, (None, None, None)),
            (258289, ('CK', None, datetime(2010, 10, 7, 15, 55, 17))),
            (410787, ('CK',
                      datetime(2010, 6, 24, 14, 20, 10),
                      datetime(2010, 6, 24, 14, 20, 28)))
        ]

        for sent_id, details in details_pairs:
            self.assertEqual(sr.details(sent_id), details)

    def test_details_error(self):
        sr = self.load_file()

        with self.assertRaises(tatoeba.InvalidIDError):
            sr.details(24)


class TatoebaSentenceReaderMiscTests(unittest.TestCase):
    def test_invalid_file(self):
        # Too few columns
        invalid_1 = StringIO('3444\teng\n3949\tjp\n')
        with self.assertRaises(tatoeba.InvalidFileError):
            sr = tatoeba.TatoebaSentenceReader(invalid_1)

        # Too many for undetailed, too few for detailed
        invalid_2 = StringIO('3444\teng\tThe boy ate a tiger\tMB')
        with self.assertRaises(tatoeba.InvalidFileError):
            sr = tatoeba.TatoebaSentenceReader(invalid_2)

        # Too many even for detailed
        invalid_3 = StringIO('3444\teng\tThe boy ate a tiger\tMB\t\\N\t\\N\t\\N')
        with self.assertRaises(tatoeba.InvalidFileError):
            sr = tatoeba.TatoebaSentenceReader(invalid_3)

class TatoebaSentenceReaderFObjTest(FileObjReaderMixin,
                                    TatoebaSentenceReaderTest):
    pass

class TatoebaSentenceReaderDetailedFObjTest(FileObjReaderMixin,
                                            TatoebaSentenceReaderDetailedTest):
    pass


###
# Tatoeba Links Reader tests

class TatoebaLinksReaderTests(ReaderBaseCase):
    _resource_name = 'links'
    ReaderClass = tatoeba.TatoebaLinksReader

    def test_basic(self):
        lr = self.load_file()

        self.assertEqual(len(lr), 29)

        groups = [
            (6381, {6381, 156245, 258289, 817971}),
            (29390, {29390, 192227}),
            (36809, {36809, 54432, 199398, 410787}),
            (46235, {46235, 208975}),
            (62093, {62093, 224758, 723598, 2031040, 2031042}),
            (68807, {68807, 231440}),
            (82526, {82526, 321190, 508870}),
            (93620, {93620, 310087, 2172488}),
            (109744, {109744, 293946}),
            (112733, {112733, 290943})
        ]

        for sent_id, group in groups:
            self.assertEqual(lr[sent_id], group)
            self.assertEqual(lr.group(sent_id), group)

    def test_filter_both(self):
        subset = {6381, 82526, 258289, 192227, 508870}

        lr = self.load_file(sentence_ids=subset, sentence_ids_filter='both')

        groups = [
            (6381, {6381, 258289}),
            (82526, {82526, 508870})
        ]

        for sent_id, group in groups:
            self.assertEqual(lr[sent_id], group)

        self.assertEqual(lr.sentence_ids_filter, 'both')

    def test_filter_sent_id(self):
        # Normally there isn't much difference between sent_id and
        # trans_id because the links file stores things redundantly, but
        # I've removed all but the 6381->817971 edge in the graph, so it
        # will show up in sent_id, but not in trans_id
        subset = {6381, 82526, 258289, 192227, 508870}
        lr = self.load_file(sentence_ids=subset, sentence_ids_filter='sent_id')

        groups = [
            (6381, {6381, 156245, 258289, 817971}),
            (82526, {82526, 321190, 508870}),
            (29390, {29390, 192227})
        ]

        for sent_id, group in groups:
            self.assertEqual(lr[sent_id], group)

        self.assertEqual(lr.sentence_ids_filter, 'sent_id')

    def test_filter_trans_id(self):
        subset = {6381, 82526, 258289, 192227, 508870}
        lr = self.load_file(sentence_ids=subset, sentence_ids_filter='trans_id')

        groups = [
            (6381, {6381, 156245, 258289}),
            (82526, {82526, 321190, 508870}),
            (29390, {29390, 192227})
        ]

        for sent_id, group in groups:
            self.assertEqual(lr[sent_id], group)

        self.assertEqual(lr.sentence_ids_filter, 'trans_id')

    def test_filter_error(self):
        subset = {6381, 82526, 258289, 192227, 508870}

        with self.assertRaises(ValueError):
            lr = self.load_file(sentence_ids=subset,
                                sentence_ids_filter='banana')

    def test_group_error(self):
        lr = self.load_file()
        with self.assertRaises(tatoeba.InvalidIDError):
            lr.group(100)

    def test_groups(self):
        lr = self.load_file(sentence_ids={6381, 156245, 29390, 192227})

        groups = [
            {6381, 156245},
            {29390, 192227}
        ]

        actual = sorted(lr.groups(), key=lambda x: min(x))

        self.assertEqual(groups, actual)
    
    def test_links(self):
        lr = self.load_file()

        self.assertEqual(lr.links, self.resource_fpath())

    def test_repr(self):
        lr = self.load_file()

        expected_fmt = "TatoebaLinksReader(links='{}')"
        expected = expected_fmt.format(self.resource_fpath())

        self.assertEqual(repr(lr), expected)


class TatoebaLinksReaderMiscTests(unittest.TestCase):
    def test_invalid_file(self):
        # Too few columns
        invalid_1 = StringIO('3444\n3949\n')
        with self.assertRaises(tatoeba.InvalidFileError):
            sr = tatoeba.TatoebaLinksReader(invalid_1)

        # Too many columns
        invalid_2 = StringIO('3444\teng\tThe boy ate a tiger\tMB')
        with self.assertRaises(tatoeba.InvalidFileError):
            sr = tatoeba.TatoebaLinksReader(invalid_2)

###
# Tanaka word tests
class TanakaWordTests(unittest.TestCase):
    def test_repr_base(self):
        pass

###
# Tatoeba Index Reader tests

class TatoebaIndexReaderTests(ReaderBaseCase):
    _resource_name = 'jpn_indices'
    ReaderClass = tatoeba.TatoebaIndexReader
    WordClass = tatoeba.TanakaWord

    def test_basic(self):
        ir = self.load_file()

        # A selection of the sentences
        sentences = {
            109744: [
                self.WordClass('彼', 'かれ', 1, None, False),
                self.WordClass('は', None, None, None, False),
                self.WordClass('英語', None, None, None, False),
                self.WordClass('が', None, None, None, False),
                self.WordClass('苦手', None, None, None, False),
                self.WordClass('だ', None, None, None, False),
                self.WordClass('が', None, 3, None, False),
                self.WordClass('数学', None, None, None, False),
                self.WordClass('で', None, None, None, False),
                self.WordClass('は', None, None, None, False), 
                self.WordClass('誰にも', None, None, None, False),
                self.WordClass('劣る', None, None, '劣らない', False)
            ],
            112733: [
                self.WordClass('彼', 'かれ', 1, None, False),
                self.WordClass('は', None, None, None, False),
                self.WordClass('其の', None, 1, 'その', False),
                self.WordClass('時', 'とき', None, None, False),
                self.WordClass('大学', None, None, None, False),
                self.WordClass('を', None, None, None, False),
                self.WordClass('卒業', None, 1, None, False),
                self.WordClass('為る', 'する', None, 'し', False),
                self.WordClass('立て', 'たて', 2, 'たて', True),
                self.WordClass('である', None, None, 'であった', False)
            ],
            192227: [
                self.WordClass('ロールプレイング', None, None, None, True),
                self.WordClass('の', None, None, None, False),
                self.WordClass('テレビゲーム', None, None, None, False),
                self.WordClass('は', None, None, None, False),
                self.WordClass('時間', None, None, None, False),
                self.WordClass('を', None, None, None, False),
                self.WordClass('食う', None, 7, None, False)
            ]
        }

        for sent_id, sent in sentences.items():
            exp_sent = sent
            act_sent = ir[sent_id]
            self.assertEqual(sent, act_sent)

            # In this case, we're going to make sure that the actual
            # .display property was actually set correctly as well
            for exp_word, act_word in zip(exp_sent, act_sent):
                self.assertEqual(exp_word.display, act_word.display)

    def test_link(self):
        ir = self.load_file()

        links = {
            82526: 321190, 93620: 310087, 109744: 293946, 112733: 290943,
            156245: 258289, 192227: 29390, 199398: 54432, 208975: 46235,
            224758: 62093, 231440: 68807
        }

        for sent_id, link_id in links.items():
            self.assertEqual(link_id, ir.link(sent_id))

    def test_link_error(self):
        ir = self.load_file()

        with self.assertRaises(tatoeba.InvalidIDError):
            ir.link(1224)


class TatoebaIndexReaderEdictTests(TatoebaIndexReaderTests):
    ReaderClass = partial(tatoeba.TatoebaIndexReader, edict=get_edict())

    def test_basic(self):
        ir = self.load_file()

        # A selection of the sentences
        sentences = {
            109744: [
                self.WordClass('彼', 'かれ', 1, None, False),
                self.WordClass('は', None, None, None, False),
                self.WordClass('英語', 'えいご', None, None, False),
                self.WordClass('が', None, None, None, False),
                self.WordClass('苦手', 'にがて', None, None, False),
                self.WordClass('だ', None, None, None, False),
                self.WordClass('が', None, 3, None, False),
                self.WordClass('数学', 'すうがく', None, None, False),
                self.WordClass('で', None, None, None, False),
                self.WordClass('は', None, None, None, False), 
                self.WordClass('誰にも', 'だれにも', None, None, False),
                self.WordClass('劣る', 'おとる', None, '劣らない', False)
            ],
            112733: [
                self.WordClass('彼', 'かれ', 1, None, False),
                self.WordClass('は', None, None, None, False),
                self.WordClass('其の', 'その', 1, 'その', False),
                self.WordClass('時', 'とき', None, None, False),
                self.WordClass('大学', 'だいがく', None, None, False),
                self.WordClass('を', None, None, None, False),
                self.WordClass('卒業', 'そつぎょう', 1, None, False),
                self.WordClass('為る', 'する', None, 'し', False),
                self.WordClass('立て', 'たて', 2, 'たて', True),
                self.WordClass('である', None, None, 'であった', False)
            ],
            192227: [
                self.WordClass('ロールプレイング', None, None, None, True),
                self.WordClass('の', None, None, None, False),
                self.WordClass('テレビゲーム', None, None, None, False),
                self.WordClass('は', None, None, None, False),
                self.WordClass('時間', 'じかん', None, None, False),
                self.WordClass('を', None, None, None, False),
                self.WordClass('食う', 'くう', 7, None, False)
            ]
        }

        for sent_id, sent in sentences.items():
            exp_sent = sent
            act_sent = ir[sent_id]
            self.assertEqual(sent, act_sent)

            # In this case, we're going to make sure that the actual
            # .display property was actually set correctly as well
            for exp_word, act_word in zip(exp_sent, act_sent):
                self.assertEqual(exp_word.display, act_word.display)