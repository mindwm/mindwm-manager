import pyte


class Sanitizer:
#    word_buf = []
#    line_buf = []
    delims = [b" ", b"\t", b"\r", b"\n"]
#    line_delims = [b"\r", b"\n"]

    def __init__(self, rows=1, columns=120):
        self.rows = rows
        self.cols = columns
        self.init_tty()

    def init_tty(self):
        self.screen = pyte.Screen(self.cols, self.rows)
        self.stream = pyte.ByteStream(self.screen)

    def clean(self):
        if self.screen:
            self.screen.reset()

    def feed_word(self, bs):
        if bs in self.delims:
            return bs

        #self.stream.feed(bytes(bs, encoding='utf-8'))
        self.stream.feed(bs)
        result = self.screen.display[0].strip()
        self.clean()
        return result

#    def feed_byte(self, byte):
#        if byte in word_delims:
#            line_buf.append(word_buf)
#            word_buf.clear()
#        else:
#            word_buf.append(byte)
#
#        stream.feed(bytes(dirty_word, encoding='utf-8'))
