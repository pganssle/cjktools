# -*- coding: utf-8 -*-
#
#  tatoeba.py
#  cjktools
#

import re
import csv
import itertools

from datetime import datetime
from collections import defaultdict, Mapping

from six import raise_from, iteritems

from cjktools.common import sopen, _NullContextWrapper


class TatoebaDict(Mapping):
    def __getitem__(self, key):
        return self._base_dict.__getitem__(key)

    def __iter__(self):
        return self._base_dict.__iter__()

    def __len__(self):
        return self._base_dict.__len__()


class TatoebaReader(TatoebaDict):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError('This is an abstract base class '
                                  'and should not be instantiated')

    def load_file(self, fpath_or_buf, **csv_kwargs):
        """
        A generator reading a given file line by line.

        :param fpath_or_buf:
            This can either be a file path or open file buffer.

        :param csv_kwargs:
            By default, the kwargs passed to :py:func:`csv.reader` are those for
            a standard Tatoeba file. You can pass additional keyword arguments
            here.
        """
        reader_kwargs = dict(delimiter='\t')
        reader_kwargs.update(csv_kwargs)

        if getattr(fpath_or_buf, 'read', None) is None:
            cfile = sopen(fpath_or_buf, mode='r')
        else:
            cfile = _NullContextWrapper(fpath_or_buf)

        with cfile as f:
            reader = csv.reader(f, **reader_kwargs)

            for row in reader:
                yield row

    def _get_src_repr(self, src):
        """ Get the string representation of the source (filename or repr) """
        if getattr(src, 'read', None) is None:
            return src
        else:
            return getattr(src, 'filename', repr(src))


class TatoebaSentenceReader(TatoebaReader):
    def __init__(self, sentences, languages={'jpn', 'eng'}):
        self.languages = languages
        self.sentences = sentences

    def language(self, sent_id):
        """
        Retrieve the language of a given sentence.

        :param sent_id:
            A valid sentence id.

        :raises InvalidIDError:
            Raised if an invalid ID is passed.

        :return:
            Returns a string indicating the language of the sentence.
        """
        for lang, sent_id_set in iteritems(self._language_dict):
            if sent_id in sent_id_set:
                return lang

        raise InvalidIDError('No language found '
                             'for sentence id {}'.format(sent_id))

    def sentence(self, sent_id):
        """
        Retrieve a sentence given a sentence ID.

        :param sent_id:
            A valid sentence id.

        :raises InvalidIDError:
            Raised if an invalid ID is passed.
        """
        try:
            return self[sent_id]
        except KeyError as e:
            raise_from(InvalidIDError('Could not find sentence '
                                      'with ID {}'.format(sent_id)), e)

    def details(self, sent_id):
        """
        Retrieve additional details about a given sentence.

        :param sent_id:
            A valid sentence ID.

        :raises MissingDataError:
            Raised if detailed sentence information was not loaded into the
            reader.

        :raises InvalidIDError:
            Raised if an invalid sentence ID is passed.

        :returns:
            Returns a tuple of the form:

            ``(username, date_added, date_modified)``

            All three are strings. 
        """
        if self._detailed_info_dict is None:
            raise MissingDataError('Detailed information not loaded.')

        try:
            return self._detailed_info_dict[sent_id]
        except KeyError as e:
            raise_from(InvalidIDError('Detailed information not found for '
                                      'sentence ID {}'.format(sent_id)), e)

    @property
    def sentences(self):
        """
        The source of the sentences that have been read.
        """
        return self._sentences_src

    @sentences.setter
    def sentences(self, src):
        self._sentences_src = self._get_src_repr(src)

        sentence_gen = self.load_file(src)

        # Infer if this is sentences or sentences_detailed
        first_row = next(sentence_gen)
        if len(first_row) == 3:
            sentences_detailed = False
        elif len(first_row) == 6:
            sentences_detailed = True
        else:
            raise InvalidFileError('Invalid sentences file, files'
                                   'must have either 3 or 6 columns.')

        # Prepare output dictionaries
        language_dict = defaultdict(set)
        sentence_dict = {}

        if sentences_detailed:
            detailed_info_dict = {}
        else:
            detailed_info_dict = None

        # Read in all rows
        for row in itertools.chain([first_row], sentence_gen):
            if self.filter_row(row):
                continue

            sent_id, lang, text = row[0:3]

            if self.languages is not None and lang not in self.languages:
                continue

            sent_id = int(sent_id)

            language_dict[lang].add(sent_id)
            sentence_dict[sent_id] = text

            if sentences_detailed:
                uname, d_added, d_modified = row[3:6]

                uname = None if uname == r'\N' else uname
                d_added, d_modified = map(self.parse_date,
                                          (d_added, d_modified))

                detailed_info_dict[sent_id] = (uname, d_added, d_modified)

        # Assign the read dictionaries
        self._language_dict = dict(language_dict)
        self._sentence_dict = sentence_dict
        self._detailed_info_dict = detailed_info_dict

    @property
    def sentence_ids(self):
        """
        All the sentence ids that have been loaded into the reader.
        """
        return self._sentence_dict.keys()

    @property
    def _base_dict(self):
        return self._sentence_dict

    datetime_format = '%Y-%m-%d %H:%M:%S'
    def parse_date(self, dtstr):
        """
        Parser for dates in detailed information.
        """
        if dtstr == r'\N':
            return None

        return datetime.strptime(dtstr, self.datetime_format)

    def filter_row(self, row):
        return False

    def __repr__(self):
        return "{}(sentences='{}')".format(self.__class__.__name__,
                                           self.sentences)


class TatoebaLinksReader(TatoebaReader):
    def __init__(self, links, sentence_ids=None, sentence_ids_filter='both'):
        """
        A class which reads a Tatoeba links.csv file.

        :param links:
            A file path or file-like object pointing to the links.csv file.

        :param sentence_ids:
            If passed, this restricts which links will be read in to those where
            both the sentence and its translation are on the list of sentence
            IDs. By default, no restriction is imposed.

        :param sentence_ids_filter:
            A string representing how sentence ids are filtered. The options
            are:
                * ``'sent_id'``: Filter only on the sentence id.
                * ``'trans_id'``: Filter only on the translation id.
                * ``'both'``: Filter on both sentence id and translation id.
        """
        self._sentence_ids_filter_str = None
        self._sentence_id_subset(sentence_ids)
        self._sentence_ids_filter(sentence_ids_filter)
        self.links = links

    def group(self, sent_id):
        """
        Retrieve the group of linked sentences that a given sentence belongs to.

        :param sent_id:
            A valid sentence ID.

        :raises InvalidIDError:
            Raised if the sentence is not in any of the linked groups

        :return:
            Returns a :py:class:`frozenset` of sentence IDs which form a
            translation group.
        """

        try:
            return self[sent_id]
        except KeyError as e:
            raise_from(InvalidIDError('Could not find sentence ID '
                                      '{} in any groups'.format(sent_id)), e)

    def groups(self):
        """
        Retrieves a list of all translation groups.

        :return:
            Returns a :py:class:`list` of :py:class:`frozenset` instances
            containing sentence IDs which form a translation group.
        """
        return list(self._group_dict.values())

    @property
    def links(self):
        return self._links_src

    @links.setter
    def links(self, src):
        self._links_src = self._get_src_repr(src)

        link_dict = {}
        group_dict = {}

        nodes = 0
        for row in self.load_file(src):
            try:
                sent_id, trans_id = map(int, row)
            except ValueError as e:
                raise_from(InvalidFileError('Invalid links file - '
                                            'files must have 2 columns'), e)
            
            # Check if both endpoints are in the sentence_id_subset
            if ((self._filter_sent and
                 sent_id not in self.sentence_id_subset) or
                (self._filter_trans and
                 trans_id not in self.sentence_id_subset)): 
                continue

            # If the sentence ID is a translation of something we've already
            # seen before, get the existing node location. Otherwise, add a new
            # node
            if sent_id in link_dict:
                node_id = link_dict[sent_id]
                new_ids = {trans_id}
            elif trans_id in link_dict:
                node_id = link_dict[trans_id]
                new_ids = {sent_id}
            else:
                node_id = nodes
                nodes += 1
                new_ids = {trans_id, sent_id}

            group_dict.setdefault(node_id, set())
            group_dict[node_id] |= new_ids
            link_dict.update({k: node_id for k in new_ids})

        self._link_dict = link_dict
        self._group_dict = {k: frozenset(v) for k, v in iteritems(group_dict)}

    @property
    def sentence_ids_filter(self):
        return self._sentence_ids_filter_str

    def _sentence_ids_filter(self, valstr):
        filter_values = {'sent_id': (True, False),
                         'trans_id': (False, True),
                         'both': (True, True)}

        valstr = valstr.lower()
        if valstr not in filter_values:
            raise ValueError('Invalid sentence_ids_filter: {}'.format(valstr))

        if self.sentence_id_subset is None:
            vals = (False, False)
        else:
            vals = filter_values[valstr]

        self._filter_sent, self._filter_trans = vals
        self._sentence_ids_filter_str = valstr

    @property
    def sentence_id_subset(self):
        return self._sentence_id_subset

    def _sentence_id_subset(self, value):
        self._sentence_id_subset = set(value) if value is not None else None

    @property
    def _base_dict(self):
        return self._link_dict
    
    def __getitem__(self, key):
        return self._group_dict[self._link_dict[key]]

    def __repr__(self):
        return "{}(links='{}')".format(self.__class__.__name__, self.links)


class TanakaWord(object):
    __slots__ = ['headword', 'reading', 'sense', 'display', 'example']

    def __init__(self, headword, reading, sense, display, example):
        self.display = display
        self.reading = reading
        self.headword = headword
        self.sense = sense
        self.example = example

    def __repr__(self):
        base = self.headword
        if self.reading:
            base += u'({})'.format(self.reading)
        if self.sense:
            base += u'[{}]'.format(self.sense)
        if self.display:
            base += u'{{{}}}'.format(self.display)
        if self.example:
            base += u'~'

        return base

    def resolve_display(self):
        return self.display if self.display is not None else self.headword

    def __eq__(self, other):
        """
        Two TanakaWords are equal if all their components are equal, with the
        exception made that setting ``display`` to ``None`` resolves ``display``
        to the headword, and so the output of ``resolve_display()`` is compared
        in that case.

        It is worth noting that even though ``example`` is context-specific,
        this is still part of the comparator.
        """
        try:
            return (
                self.headword == other.headword and
                self.sense == other.sense and
                self.example == other.example and
                self.reading == other.reading and
                self.resolve_display() == other.resolve_display()
            )
        except AttributeError:
            return NotImplemented

    def __neq__(self, other):
        return not self == other


class TatoebaIndexReader(TatoebaReader):
    """
    A class for reading and parsing the Sentence-Dictionary linking Tatoeba
    files (``jpn_indices``). More information on this format can be found
    `here <http://www.edrdg.org/wiki/index.php/Sentence-Dictionary_Linking>`_.
    """
    WordClass = TanakaWord
    sentence_splitter = lambda self, x: x.split(' ')

    def __init__(self, jpn_indices, edict=None, sentence_ids=None):
        """
        :param jpn_indices:
            A file path or file object in the Tanaka corpus sentence linking
            format.

        :param edict:
            An EDICT file in which to look up head words which may be missing
            readings.

        :param sentence_inds:
            A subset of all sentence indices to load.
        """
        self.sentence_id_subset = sentence_ids
        self.edict = edict
        self.jpn_indices = jpn_indices

    def link(self, sent_id):
        """
        Retrieve the sentence ID of the linked English translation as provided
        by the ``jpn_indices`` corpus.

        :param sent_id:
            A valid sentence ID.

        :raises InvalidIDError:
            Raised if an invalid ID is passed.

        :return:
            Returns a numeric sentence ID.
        """
        try:
            return self._link_dict[sent_id]
        except KeyError as e:
            raise_from(
                InvalidIDError('Sentence ID {} not found'.format(sent_id)),
                e)

    @property
    def jpn_indices(self):
        return self._jpn_indices_src

    @jpn_indices.setter
    def jpn_indices(self, src):
        self._jpn_indices_src = self._get_src_repr(src)

        sentence_gen = self.load_file(src)

        sentence_dict = {}
        link_dict = {}

        for row in sentence_gen:
            sent_id, meaning_id, text = row
            sent_id, meaning_id = map(int, (sent_id, meaning_id))

            link_dict[sent_id] = meaning_id

            sentence = self.parse_sentence(text)
            sentence = self.adjust_details(sentence)

            sentence_dict[sent_id] = sentence

        self._sentence_dict = sentence_dict
        self._link_dict = link_dict

    word_re = re.compile(r'(?P<headword>[^\(\[\{\|\~]+)'
                         r'(?:\((?P<reading>[^\)]+)\))?'
                         r'(?:\[(?P<sense>[\d]+)\])?'
                         r'(?:\{(?P<display>[^\}]+)\})?'
                         r'(?:(?P<example>\~))?'
                         r'(?:|\d+)')

    def parse_sentence(self, text):
        """
        Takes a Tanaka corpus formatted sentence and parses it into tagged
        :class:`TatoebaIndexReader.WordClass` (by default :class:`TanakaWord`)
        word objects.

        :param text:
            A Tanaka-corpus formatted sentence.

        :return:
            Returns a :py:class:`list` of :class:`TatoebaIndexReader.WordClass`
            objects representing a given sentence.
        """
        words = self.sentence_splitter(text)
        sentence = []
        for word in words:
            if not len(word):
                continue

            m = self.word_re.match(word)
            if m is None:
                raise InvalidEntryError(('Could not interpret word {} in '
                                        'sentence:\n{}').format(word, text))

            kwargs = {k: m.group(k) for k in self.word_re.groupindex.keys()}
            if kwargs['sense'] is not None:
                kwargs['sense'] = int(kwargs['sense'])
            kwargs['example'] = kwargs['example'] is not None
            sentence.append(self.WordClass(**kwargs))

        return sentence

    def adjust_details(self, sentence):
        """
        Given a sentence as parsed by `parse_sentence`, this tries to fill in
        implied data using the ``edict`` dictionary supplied to the constructor.

        :param sentence:
            A :py:class:`list` of :class:`TatoebaIndexReader.WordClass` objects,
            as output by :func:`parse_sentence`. The items of this list will
            be mutated.

        :return:
            Returns the input ``sentence``, adjusted with additional details
            from the ``edict`` supplied. If ``edict`` is not supplied, no
            changes will be made.
        """
        if self.edict is None:
            return sentence

        for word in sentence:
            # The only one that is guaranteed to be present is the headword.
            if word.headword not in self.edict:
                continue

            if word.reading is None:
                ee = self.edict[word.headword]
                reading = None
                if word.sense is not None and word.sense <= len(ee.readings):
                    # As far as I can tell, jpn_indices uses a 0-based index.
                    reading = ee.readings[word.sense - 1]
                else:
                    if len(set(ee.readings)) == 1:
                        reading = ee.readings[0]

                if reading != word.headword:
                    word.reading = reading

        return sentence


    @property
    def sentence_id_subset(self):
        return self._sentence_id_subset

    @sentence_id_subset.setter
    def sentence_id_subset(self, value):
        self._sentence_id_subset = set(value) if value is not None else None

    @property
    def _base_dict(self):
        return self._sentence_dict


class MissingDataError(ValueError):
    pass

class InvalidFileError(ValueError):
    pass

class InvalidIDError(KeyError):
    pass

class InvalidEntryError(ValueError):
    pass
