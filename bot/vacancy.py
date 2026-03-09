class Vacancy:
    def __init__(self, title, employer, href, element=None):
        self.title = (title or "").strip()
        self.employer = (employer or "").strip()
        self.href = href
        self.element = element