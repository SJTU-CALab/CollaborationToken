import enum


class ExecErrorType(enum.Enum):
    EMPTY = 0
    SYMBOL_EXEC = 1
    SYMBOL_TIMEOUT = 2
    COMPILATION = 3


class Context:

    def __init__(self, start, project_dir, src_file, diff, request_id,
                 platform='', ast_abstracts=[], cfg_abstracts=[], ssg_abstracts=[]):
        self.start = start  # start time
        self.request_id = request_id  # request id

        # input project dir and file dir
        self.project_dir = project_dir
        self.src_file = src_file

        # different lines between commit before and after
        self.diff = diff  # i.e. [1,2,3]

        # platform for analysis files
        # todo: not used now
        self.platform = platform

        # default compilation config
        self.include_paths = ["."]
        self.remaps = {}
        self.root_path = self.project_dir
        self.allow_paths = []

        # default index for abstracts
        self.ast_abstracts = ast_abstracts

        self.cfg_abstracts = cfg_abstracts

        self.ssg_abstracts = ssg_abstracts

        # if analysis cause an error
        self.err = False
        self.error_type = ExecErrorType.EMPTY
        self.index_error = set()
        # timeout
        self.timeout = False
        # file content source
        self.source = None

    def set_timeout(self):
        self.timeout = True

    def set_err(self, error_type):
        self.err = True
        self.error_type = error_type

    def set_index_err(self, index):
        self.index_error.add(index)

    def is_index_err(self, index):
        return index in self.index_error

    def add_include_path(self, path):
        self.include_paths.append(path)

    def add_remap(self, key, value):
        self.remaps[key] = value

    def add_ast_abstract(self, index):
        self.ast_abstracts.append(index)

    def add_cfg_abstract(self, index):
        self.cfg_abstracts.append(index)

    def add_ssg_abstract(self, index):
        self.ssg_abstracts.append(index)

    def set_source(self, source):
        self.source = source

    def get_source(self):
        return self.source

    def get_diff(self):
        return self.diff