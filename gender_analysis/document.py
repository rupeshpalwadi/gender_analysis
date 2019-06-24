import re
import string
from collections import Counter
from pathlib import Path

from more_itertools import windowed

import nltk

# nltk as part of speech tagger, requires these two packages
nltk.download('punkt', quiet=True)
nltk.download('averaged_perceptron_tagger', quiet=True)
gutenberg_imported = True

from gender_analysis import common
from ast import literal_eval


try:
    from gutenberg.cleanup import strip_headers
except ImportError:
    # print('Cannot import gutenberg')
    gutenberg_imported = False

from gender_analysis.common import TEXT_END_MARKERS, TEXT_START_MARKERS, LEGALESE_END_MARKERS, \
    LEGALESE_START_MARKERS


class Document(common.FileLoaderMixin):
    """ The Document class loads and holds the full text and
    metadata (author, title, publication date) of a document

    >>> from gender_analysis import document
    >>> document_metadata = {'gutenberg_id': '105', 'author': 'Austen, Jane', 'title': 'Persuasion',
    ...                   'corpus_name': 'sample_novels', 'date': '1818',
    ...                   'filename': 'austen_persuasion.txt'}
    >>> austen = document.Document(document_metadata)
    >>> type(austen.text)
    <class 'str'>
    >>> len(austen.text)
    466879
    """

    def __init__(self, metadata_dict):
        if not isinstance(metadata_dict, dict):
            raise TypeError(
                'metadata must be passed in as a dictionary value'
            )

        # Check that the essential attributes for the document exists.
        if 'filename' not in metadata_dict:
            raise ValueError(str(metadata_dict)+f'metadata_dict must have an entry for filename')

        self.members = metadata_dict.keys()

        for key in metadata_dict:
            if hasattr(self, str(key)):
                raise KeyError(
                    'Key name ', str(key), ' is reserved in the Document class. Please use another name'
                )
            setattr(self, str(key), metadata_dict[key])

        # optional attributes
        # Check that the date is a year (4 consecutive integers)
        if 'date' in metadata_dict:
            if not re.match(r'^\d{4}$', metadata_dict['date']):
                raise ValueError('The document date should be a year (4 integers), not',
                                 f'{metadata_dict["date"]}. Full metadata: {metadata_dict}')

        try:
            self.date = int(metadata_dict['date'])
        except KeyError:
            self.date = None

        self._word_counts_counter = None
        self._word_count = None

        if 'author_gender' in metadata_dict and self.author_gender not in {'female', 'male', 'non-binary', 'unknown', 'both'}:
            raise ValueError('Author gender has to be "female", "male" "non-binary," or "unknown" ',
                             f'but not {self.author_gender}. Full metadata: {metadata_dict}')

        if not metadata_dict['filename'].endswith('.txt'):
            raise ValueError(
                f'The document filename ', str(metadata_dict['filename']), 'does not end in .txt . Full metadata: '
                f'{metadata_dict}.'
            )

        self.text = self._load_document_text()


    @property
    def word_count(self):
        """
        Lazy-loading for Document.word_count attribute. Returns the number of words in the document.
        The word_count attribute is useful for the get_word_freq function.
        However, it is performance-wise costly, so it's only loaded when it's actually required.

        >>> from gender_analysis import document
        >>> document_metadata = {'gutenberg_id': '105', 'author': 'Austen, Jane', 'title': 'Persuasion',
        ...                   'corpus_name': 'sample_novels', 'date': '1818',
        ...                   'filename': 'austen_persuasion.txt'}
        >>> austen = document.Document(document_metadata)
        >>> austen.word_count
        83285

        :return: int
        """

        if self._word_count is None:
            self._word_count = len(self.get_tokenized_text())
        return self._word_count

    def __str__(self):
        """
        Overrides python print method for user-defined objects for Document class
        Returns the filename without the extension - author and title word
        :return: str

        >>> from gender_analysis import document
        >>> document_metadata = {'gutenberg_id': '105', 'author': 'Austen, Jane', 'title': 'Persuasion',
        ...                   'corpus_name': 'sample_novels', 'date': '1818',
        ...                   'filename': 'austen_persuasion.txt'}
        >>> austen = document.Document(document_metadata)
        >>> document_string = str(austen)
        >>> document_string
        'austen_persuasion'
        """
        name = self.filename[0:len(self.filename) - 4]
        return name

    def __repr__(self):
        '''
        Overrides the built-in __repr__ method
        Returns the object type (Document) and then the filename without the extension
            in <>.

        :return: string

        >>> from gender_analysis import document
        >>> document_metadata = {'gutenberg_id': '105', 'author': 'Austen, Jane', 'title': 'Persuasion',
        ...                   'corpus_name': 'sample_novels', 'date': '1818',
        ...                   'filename': 'austen_persuasion.txt'}
        >>> austen = document.Document(document_metadata)
        >>> repr(austen)
        '<Document (austen_persuasion)>'
        '''

        name = self.filename[0:len(self.filename) - 4]
        return f'<Document ({name})>'

    def __eq__(self, other):
        """
        Overload the equality operator to enable comparing and sorting documents.

        >>> from gender_analysis.document import Document
        >>> austen_metadata = {'author': 'Austen, Jane', 'title': 'Persuasion',
        ...                   'corpus_name': 'sample_novels', 'date': '1818',
        ...                   'filename': 'austen_persuasion.txt'}
        >>> austen = Document(austen_metadata)
        >>> austen2 = Document(austen_metadata)
        >>> austen == austen2
        True
        >>> austen.text += 'no longer equal'
        >>> austen == austen2
        False

        :return: bool
        """
        if not isinstance(other, Document):
            raise NotImplementedError("Only a Document can be compared to another Document.")

        attributes_required_to_be_equal = ['filename']

        for attribute in attributes_required_to_be_equal:
            if not hasattr(other, attribute):
                raise AttributeError(f'Comparison document lacks attribute {attribute}.')
            if getattr(self, attribute) != getattr(other, attribute):
                return False

        if self.text != other.text:
            return False

        return True

    def __lt__(self, other):
        """
        Overload less than operator to enable comparing and sorting documents

        >>> from gender_analysis import document
        >>> austen_metadata = {'author': 'Austen, Jane', 'title': 'Persuasion',
        ...                   'corpus_name': 'sample_novels', 'date': '1818',
        ...                   'filename': 'austen_persuasion.txt'}
        >>> austen = document.Document(austen_metadata)
        >>> hawthorne_metadata = {'author': 'Hawthorne, Nathaniel', 'title': 'Scarlet Letter',
        ...                   'corpus_name': 'sample_novels', 'date': '1850',
        ...                   'filename': 'hawthorne_scarlet.txt'}
        >>> hawthorne = document.Document(hawthorne_metadata)
        >>> hawthorne < austen
        False
        >>> austen < hawthorne
        True

        :return: bool
        """
        if not isinstance(other, Document):
            raise NotImplementedError("Only a Document can be compared to another Document.")

        return self.filename < other.filename

    def __hash__(self):
        """
        Makes the Document object hashable

        :return:
        """

        return hash(repr(self))

    def _load_document_text(self):
        """Loads the text of a document and uses the remove_boilerplate_text() and
        remove_table_of_contents() functions on the text of the document to remove the boilerplate
        text and table of contents from the document. After these actions, the document's text should be
        only the actual text of the document.

        Is a private function as it is unnecessary to access it outside the class.

        Currently only supports boilerplate removal for Project gutenberg ebooks.

        :return: str
        """
        if self.corpus_name == 'sample_novels':
            file_path = Path('corpora', self.corpus_name, 'texts', self.filename)
        else:
            file_path = Path('corpora', self.corpus_name, self.filename)


        try:
            text = self.load_file(file_path)
        except FileNotFoundError:
            err = "Could not find the document text file "
            err += "at the expected location ({file_path})."
            raise FileNotFoundError(err)

        # This function will remove the boilerplate text from the document's text. It has been
        # placed into a separate function in the case that other document text cleaning functions
        # want to be added at a later date.
        text = self._remove_boilerplate_text(text)

        return text

    def _remove_boilerplate_text(self, text):
        """
        Removes the boilerplate text from an input string of a document.
        Currently only supports boilerplate removal for Project Gutenberg ebooks. Uses the
        strip_headers() function from the gutenberg module, which can remove even nonstandard
        headers.

        (see book number 3780 for one example of a nonstandard header — james_highway.txt in our
        sample corpus; or book number 105, austen_persuasion.txt, which uses the standard Gutenberg
        header but has had some info about the ebook's production inserted after the standard
        boilerplate).

        :return: str

        >>> from gender_analysis import document
        >>> document_metadata = {'author': 'Austen, Jane', 'title': 'Persuasion',
        ...                   'corpus_name': 'sample_novels', 'date': '1818',
        ...                   'filename': 'james_highway.txt'}
        >>> austen = document.Document(document_metadata)
        >>> file_path = Path('corpora', austen.corpus_name, 'texts', austen.filename)
        >>> raw_text = austen.load_file(file_path)
        >>> raw_text = austen._remove_boilerplate_text(raw_text)
        >>> title_line = raw_text.splitlines()[0]
        >>> title_line
        "THE KING'S HIGHWAY"

        TODO: neither version of remove_boilerplate_text works on Persuasion, and it doesn't look like it's
        easily fixable
        """

        # the gutenberg books are stored locally with the boilerplate already removed
        # (removing the boilerplate is slow and would mean that just loading the corpus would take
        # up to 5 minutes
        if self.corpus_name == 'gutenberg':
            return text

        if gutenberg_imported:
            return strip_headers(text).strip()
        else:
            return self._remove_boilerplate_text_without_gutenberg(text)

    def _remove_boilerplate_text_without_gutenberg(self, text):
        """
        Removes the boilerplate text from an input string of a document.
        Currently only supports boilerplate removal for Project Gutenberg ebooks. Uses the
        strip_headers() function, somewhat inelegantly copy-pasted from the gutenberg module, which can remove even nonstandard
        headers.

        (see book number 3780 for one example of a nonstandard header — james_highway.txt in our
        sample corpus; or book number 105, austen_persuasion.txt, which uses the standard Gutenberg
        header but has had some info about the ebook's production inserted after the standard
        boilerplate).

        :return: str

        >>> from gender_analysis import document
        >>> document_metadata = {'author': 'Austen, Jane', 'title': 'Persuasion',
        ...                   'corpus_name': 'sample_novels', 'date': '1818',
        ...                   'filename': 'james_highway.txt'}
        >>> austen = document.Document(document_metadata)
        >>> file_path = Path('corpora', austen.corpus_name, 'texts', austen.filename)
        >>> raw_text = austen.load_file(file_path)
        >>> raw_text = austen._remove_boilerplate_text_without_gutenberg(raw_text)
        >>> title_line = raw_text.splitlines()[0]
        >>> title_line
        "THE KING'S HIGHWAY"
        """

        # new method copy-pasted from Gutenberg library
        lines = text.splitlines()
        sep = '\n'

        out = []
        i = 0
        footer_found = False
        ignore_section = False

        for line in lines:
            reset = False

            if i <= 600:
                # Check if the header ends here
                if any(line.startswith(token) for token in TEXT_START_MARKERS):
                    reset = True

                # If it's the end of the header, delete the output produced so far.
                # May be done several times, if multiple lines occur indicating the
                # end of the header
                if reset:
                    out = []
                    continue

            if i >= 100:
                # Check if the footer begins here
                if any(line.startswith(token) for token in TEXT_END_MARKERS):
                    footer_found = True

                # If it's the beginning of the footer, stop output
                if footer_found:
                    break

            if any(line.startswith(token) for token in LEGALESE_START_MARKERS):
                ignore_section = True
                continue
            elif any(line.startswith(token) for token in LEGALESE_END_MARKERS):
                ignore_section = False
                continue

            if not ignore_section:
                out.append(line.rstrip(sep))
                i += 1

        return sep.join(out).strip()

    def get_tokenized_text(self):
        """
        Tokenizes the text and returns it as a list of tokens

        This is a very simple way of tokenizing the text. We will replace it soon with a
        better implementation that uses either regex or nltk
        E.g. this version doesn't handle dashes or contractions

        >>> from gender_analysis import document
        >>> document_metadata = {'author': 'Austen, Jane', 'title': 'Persuasion', 'date': '1818',
        ...                   'corpus_name': 'document_test_files', 'filename': 'test_text_1.txt'}
        >>> austin = document.Document(document_metadata)
        >>> tokenized_text = austin.get_tokenized_text()
        >>> tokenized_text
        ['allkinds', 'of', 'punctuation', 'and', 'special', 'chars']

        :rtype: list
        """

        # Excluded characters: !"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~
        excluded_characters = set(string.punctuation)
        cleaned_text = ''
        for character in self.text:
            if character not in excluded_characters:
                cleaned_text += character

        tokenized_text = cleaned_text.lower().split()
        return tokenized_text

    def find_quoted_text(self):
        """
        Finds all of the quoted statements in the document text

        >>> from gender_analysis import document
        >>> test_text = '"This is a quote" and also "This is my quote"'
        >>> document_metadata = {'author': 'Austen, Jane', 'title': 'Persuasion',
        ...                   'corpus_name': 'document_test_files', 'date': '1818',
        ...                   'filename': 'test_text_0.txt'}
        >>> document_novel = document.Document(document_metadata)
        >>> document_novel.find_quoted_text()
        ['"This is a quote"', '"This is my quote"']

        # TODO: Make this test pass
        # >>> test_document.text = 'Test case: "Miss A.E.--," [...] "a quote."'
        # >>> test_document.find_quoted_text()
        # ['"Miss A.E.-- a quote."']

        # TODO: Make this test pass
        # One approach would be to find the shortest possible closed quote.
        #
        # >>> test_document.text = 'Test case: "Open quote. [...] "Closed quote."'
        # >>> test_document.find_quoted_text()
        # ['"Closed quote."']

        TODO(Redlon & Murray): Add and statements so that a broken up quote is treated as a
        TODO(Redlon & Murray): single quote
        TODO: Look for more complicated test cases in our existing documents.

        :return: list of complete quotation strings
        """
        text_list = self.text.split()
        quotes = []
        current_quote = []
        quote_in_progress = False
        quote_is_paused = False

        for word in text_list:
            if word[0] == "\"":
                quote_in_progress = True
                quote_is_paused = False
                current_quote.append(word)
            elif quote_in_progress:
                if not quote_is_paused:
                    current_quote.append(word)
                if word[-1] == "\"":
                    if word[-2] != ',':
                        quote_in_progress = False
                        quote_is_paused = False
                        quotes.append(' '.join(current_quote))
                        current_quote = []
                    else:
                        quote_is_paused = True

        return quotes

    def get_count_of_word(self, word):
        """
        Returns the number of instances of str word in the text.  N.B.: Not case-sensitive.
        >>> from gender_analysis import document
        >>> document_metadata = {'author': 'Hawthorne, Nathaniel', 'title': 'Scarlet Letter',
        ...                   'corpus_name': 'document_test_files', 'date': '2018',
        ...                   'filename': 'test_text_2.txt'}
        >>> scarlett = document.Document(document_metadata)
        >>> scarlett.get_count_of_word("sad")
        4
        >>> scarlett.get_count_of_word('ThisWordIsNotInTheWordCounts')
        0

        :param word: word to be counted in text
        :return: int
        """

        # If word_counts were not previously initialized, do it now and store it for the future.
        if not self._word_counts_counter:
            self._word_counts_counter = Counter(self.get_tokenized_text())

        return self._word_counts_counter[word]

    def get_wordcount_counter(self):
        """
        Returns a counter object of all of the words in the text.
        (The counter can also be accessed as self.word_counts. However, it only gets initialized
        when a user either runs Document.get_count_of_word or Document.get_wordcount_counter, hence
        the separate method.)

        >>> from gender_analysis import document
        >>> document_metadata = {'author': 'Hawthorne, Nathaniel', 'title': 'Scarlet Letter',
        ...                   'corpus_name': 'document_test_files', 'date': '2018',
        ...                   'filename': 'test_text_10.txt'}
        >>> scarlett = document.Document(document_metadata)
        >>> scarlett.get_wordcount_counter()
        Counter({'was': 2, 'convicted': 2, 'hester': 1, 'of': 1, 'adultery': 1})

        :return: Counter
        """

        # If word_counts were not previously initialized, do it now and store it for the future.
        if not self._word_counts_counter:
            self._word_counts_counter = Counter(self.get_tokenized_text())
        return self._word_counts_counter

    def words_associated(self, word):
        """
        Returns a counter of the words found after given word
        In the case of double/repeated words, the counter would include the word itself and the next
        new word
        Note: words always return lowercase

        >>> from gender_analysis import document
        >>> document_metadata = {'author': 'Hawthorne, Nathaniel', 'title': 'Scarlet Letter',
        ...                   'corpus_name': 'document_test_files', 'date': '2018',
        ...                   'filename': 'test_text_11.txt'}
        >>> scarlett = document.Document(document_metadata)
        >>> scarlett.words_associated("his")
        Counter({'cigarette': 1, 'speech': 1})

        :param word:
        :return: a Counter() object with {word:occurrences}
        """
        word = word.lower()
        word_count = Counter()
        check = False
        text = self.get_tokenized_text()

        for w in text:
            if check:
                word_count[w] += 1
                check = False
            if w == word:
                check = True
        return word_count

    def get_word_windows(self, search_terms, window_size=2):
        """
        Finds all instances of `word` and returns a counter of the words around it.
        window_size is the number of words before and after to return, so the total window is
        2x window_size + 1

        >>> from gender_analysis.document import Document
        >>> document_metadata = {'author': 'Hawthorne, Nathaniel', 'title': 'Scarlet Letter',
        ...                   'corpus_name': 'document_test_files', 'date': '2018',
        ...                   'filename': 'test_text_12.txt'}
        >>> scarlett = Document(document_metadata)

        # search_terms can be either a string...
        >>> scarlett.get_word_windows("his", window_size=2)
        Counter({'he': 1, 'lit': 1, 'cigarette': 1, 'and': 1, 'then': 1, 'began': 1, 'speech': 1, 'which': 1})

        # ... or a list of strings
        >>> scarlett.get_word_windows(['purse', 'tears'])
        Counter({'her': 2, 'of': 1, 'and': 1, 'handed': 1, 'proposal': 1, 'drowned': 1, 'the': 1})

        :param search_terms
        :param window_size: int
        :return: Counter
        """

        if isinstance(search_terms, str):
            search_terms = [search_terms]

        search_terms = set(i.lower() for i in search_terms)

        counter = Counter()

        for text_window in windowed(self.get_tokenized_text(), 2 * window_size + 1):
            if text_window[window_size] in search_terms:
                for surrounding_word in text_window:
                    if not surrounding_word in search_terms:
                        counter[surrounding_word] += 1

        return counter

    def get_word_freq(self, word):
        """
        Returns dictionary with key as word and value as the frequency of appearance in book
        :param words: str
        :return: double

        >>> from gender_analysis import document
        >>> document_metadata = {'author': 'Hawthorne, Nathaniel', 'title': 'Scarlet Letter',
        ...                   'corpus_name': 'document_test_files', 'date': '1900',
        ...                   'filename': 'test_text_2.txt'}
        >>> scarlett = document.Document(document_metadata)
        >>> frequency = scarlett.get_word_freq('sad')
        >>> frequency
        0.13333333333333333
        """

        word_frequency = self.get_count_of_word(word) / self.word_count
        return word_frequency

    def get_part_of_speech_tags(self):
        """
        Returns the part of speech tags as a list of tuples. The first part of each tuple is the
        term, the second one the part of speech tag.
        Note: the same word can have a different part of speech tag. In the example below,
        see "refuse" and "permit"
        >>> from gender_analysis.document import Document
        >>> document_metadata = {'author': 'Hawthorne, Nathaniel', 'title': 'Scarlet Letter',
        ...                   'corpus_name': 'document_test_files', 'date': '1900',
        ...                   'filename': 'test_text_13.txt'}
        >>> document = Document(document_metadata)
        >>> document.get_part_of_speech_tags()[:4]
        [('They', 'PRP'), ('refuse', 'VBP'), ('to', 'TO'), ('permit', 'VB')]
        >>> document.get_part_of_speech_tags()[-4:]
        [('the', 'DT'), ('refuse', 'NN'), ('permit', 'NN'), ('.', '.')]

        :rtype: list
        """
        text = nltk.word_tokenize(self.text)
        pos_tags = nltk.pos_tag(text)
        return pos_tags


if __name__ == '__main__':
    from dh_testers.testRunner import main_test

    main_test()
