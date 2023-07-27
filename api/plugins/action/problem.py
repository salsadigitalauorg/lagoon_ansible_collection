import json
from . import LagoonActionBase
from ansible.errors import AnsibleError
from ansible.utils.display import Display


display = Display()

SEVERITY_VALUES = ["NONE", "UNKNOWN", "NEGLIGIBLE",
                   "LOW", "MEDIUM", "HIGH", "CRITICAL"]

class ActionModule(LagoonActionBase):

    def run(self, tmp=None, task_vars=None):

        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp

        self._display.v("Task args: %s" % self._task.args)

        self.createClient(task_vars)

        problemInput = {
          'associatedPackage': self._task.args.get("associatedPackage"),
          'data': self._task.args.get("data"),
          'description': self._task.args.get("description", None),
          'environment': int(self._task.args.get("environment")),
          'fixedVersion': self._task.args.get("fixedVersion"),
          'identifier': self._task.args.get("identifier"),
          'links': self._task.args.get("links"),
          'service': self._task.args.get("service"),
          'severity': self._task.args.get("severity", "NONE"),
          'severityScore': self._task.args.get("severityScore", 0),
          'source': self._task.args.get("source", None),
          'version': self._task.args.get("version", None),
        }

        # modifiers
        state = self._task.args.get('state', None)

        found_problem = False

        problems = self.get_problems(problemInput['environment'])
        for problem in problems:
            if problem["identifier"] == problemInput['identifier']:
                found_problem = problem

        if not found_problem and state == "absent":
            result["changed"] = False
        elif found_problem and state == "absent":
            result["changed"] = True
            result["result"] = self.delete_problem(
                problemInput['environment'], problemInput['identifier'])
        elif found_problem:
            if problemInput['data'] != found_problem["data"]:
                result["changed"] = True
                self.delete_problem(
                    problemInput['environment'], problemInput['identifier'])
                result["result"] = self.add_problem(problemInput)
            else:
                result["changed"] = False
        else:
            result["changed"] = True
            result["result"] = self.add_problem(problemInput)

        return result


    def get_problems(self, environment_id):
        res = self.client.execute_query(
            """
            query envProblems($environment_id: Int!) {
                environmentById(id: $environment_id) {
                    problems {
                        id
                        identifier
                        data
                        source
                    }
                }
            }""",
            {
                "environment_id": environment_id
            }
        )

        try:
            raw_problems = res["environmentById"]["problems"]
            processed_problems = []
            for problem in raw_problems:
                problem["data"] = json.loads(problem["data"])
                processed_problems.append(problem)
            return processed_problems
        except KeyError:
            return dict()

    def delete_problem(self, environment_id, name):
        res = self.client.execute_query(
            """
            mutation dp(
                $environment_id: Int!
                $identifier: String!
            ) {
                deleteProblem(input: {
                    environment: $environment_id
                    identifier: $identifier
                })
            }""",
            {
                "environment_id": environment_id,
                "identifier": name
            }
        )

        try:
            return res["deleteFact"] == "success"
        except KeyError:
            return False

    def add_problem(self, addProblemInputProvided: dict) -> dict:
        addProblemInput = {
            'associatedPackage': "",
            'description': "Provided by Lagoon Ansible collection",
            'fixedVersion': "",
            'links': "",
            'service': "",
            'severity': "NONE",
            'severityScore': 0,
            'source': "ansible",
            'version': "",
        }
        addProblemInput.update(addProblemInputProvided)

        for required in ["environment", "data", "identifier"]:
            if required not in addProblemInput:
                raise AnsibleError(f"Missing required argument: {required}")

        if not isinstance(addProblemInput['environment'], int):
            raise AnsibleError(
                f"Invalid problem environment {addProblemInput['environment']}, must be an integer")

        if not isinstance(addProblemInput['data'], dict) and not isinstance(addProblemInput['data'], list):
            raise AnsibleError(
                f"Invalid problem data '{addProblemInput['data']}', must be a dict or list, to be JSON encoded")
        addProblemInput['data'] = json.dumps(addProblemInput['data'])

        if addProblemInput['severity'] not in SEVERITY_VALUES:
            raise AnsibleError(
                f"Invalid problem severity {addProblemInput['severity']}, must be {', '.join(SEVERITY_VALUES)}")

        if not (addProblemInput['severityScore'] >= 0 and addProblemInput['severityScore'] <= 1):
            raise AnsibleError(
                f"Invalid problem severity score {addProblemInput['severityScore']}, must be between 0 and 1")

        res = self.client.execute_query(
            """
            mutation addProblem(
                $associatedPackage: String
                $data: String!
                $description: String
                $environment: Int!
                $fixedVersion: String
                $identifier: String!
                $links: String
                $service: String
                $severity: ProblemSeverityRating
                $severityScore: SeverityScore
                $source: String!
                $version: String
            ) {
                addProblem(input: {
                    associatedPackage: $associatedPackage
                    data: $data
                    description: $description
                    environment: $environment
                    fixedVersion: $fixedVersion
                    identifier: $identifier
                    links:  $links
                    service: $service
                    severity: $severity
                    severityScore: $severityScore
                    source: $source
                    version: $version
                }) {
                    id
                }
            }""", addProblemInput
        )

        return res["addProblem"]
