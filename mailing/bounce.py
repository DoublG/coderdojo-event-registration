class BounceProcessor:

    def process(self):
        with self.connect() as mailbox:
            for message in self.get_new_messages(mailbox):
                bounce = self.parse(message)

                if bounce:
                    self.handle_bounce(bounce)

    def connect(self):
        pass

    def get_new_messages(self, mailbox):
        pass

    def parse(self, message):
        pass

    def handle_bounce(self, bounce):
        pass
