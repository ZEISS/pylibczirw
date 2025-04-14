# Introduction
Thank you for considering contributing to pylibCZIrw.  

Following these guidelines helps to communicate that you respect the time of the developers managing and developing this open source project. In return, they should reciprocate that respect in addressing your issue, assessing changes, and helping you finalize your pull requests.  

pylibCZIrw is an open source project and we love to receive contributions from our community — you! There are many ways to contribute, from writing tutorials or blog posts, improving the documentation, submitting bug reports and feature requests or writing code which can be incorporated into pylibCZIrw itself.  

No matter how you intend to participate in improving pylibCZIrw - please make sure to follow our [Code of Conduct](./CODE_OF_CONDUCT.md).

# Reporting Issues
Depending on the nature of the bug/issue, the following guidelines apply:

## Security
You must never report security related issues, vulnerabilities or bugs including sensitive information to the bug/issue tracker, or elsewhere in public. Instead, please follow the guidelines set-up in [SECURITY.md](./SECURITY.md).

## Other Issues
Please revisit all previously created issues before creating a new issue.  
Choose from one of the provided templates and carefully fill out all required information.

# Suggesting a Feature
If you find yourself wishing for a feature or improvement that doesn't exist in pylibCZIrw, you are probably not alone. There are bound to be others out there with similar needs. Many of the features that pylibCZIrw has today have been added because our users saw the need. Open an issue on our issues list on GitHub which describes the feature you would like to see, why you need it, and how it should work.

# Creating a PR
We are always happy to receive code contributions from your side.  

For all contributions, please respect the following guidelines:  
- Each PR should implement ONE feature or bugfix. If you want to add or fix more than one thing, submit more than one PR.  
- Whenever possible: Associate a PR with either an [issue](#other-issues) or a [feature](#suggesting-a-feature).  
- Format your PR title according to the [angular commit guidelines](https://github.com/angular/angular.js/blob/master/DEVELOPERS.md#commits) as **```<type>(<optional scope>): <subject>```** to support proper functioning of the [python semantic release commit parsing](https://python-semantic-release.readthedocs.io/en/latest/commit-parsing.html).  
  The following prefixes (types) are allowed:  
  - **chore**: Changes to the build process or auxiliary tools and libraries such as documentation generation  
  - **docs**: Documentation only changes  
  - **feat**: A new feature [[triggers](https://github.com/ZEISS/pylibczirw/actions/workflows/build.yml) a **MINOR** update pushed to PyPI when merged to main]  
  - **fix**: A bug fix [[triggers](https://github.com/ZEISS/pylibczirw/actions/workflows/build.yml) a **PATCH** update pushed to PyPI when merged to main]  
  - **perf**: A code change that improves performance [[triggers](https://github.com/ZEISS/pylibczirw/actions/workflows/build.yml) a **PATCH** update pushed to PyPI when merged to main]  
  - **refactor**: A code change that neither fixes a bug nor adds a feature (incl. style changes that do not affect the meaning of the code like white-space, formatting, missing semi-colons, etc)  
  - **test**: Adding missing or correcting existing tests  
  - **deps**: Reserved for dependabot PR/updates  

  The final squash commit message (only squash merging allowed) is prepared to match this commit style (by taking the PR title and PR description) based on [New options for controlling the default commit message when merging a pull request - The GitHub Blog](https://github.blog/changelog/2022-08-23-new-options-for-controlling-the-default-commit-message-when-merging-a-pull-request/).  
  **DO NOT CHANGE THE FINAL COMMIT MESSAGE AS PREPARED BEFORE COMPLETING THE PR!**
- Do not commit changes to files that are irrelevant to the type and subject defined before.  
- Only once: Make sure to either sign the [Individual](./cla_individual.txt) or the [Corporate](./cla_corporate.txt) Contributor License Agreement (CLA) and send it to <github.microscopy@zeiss.com>.

**Note: The final squash commit message must match angular commit style as defined in PR YAML check or default merge commit message start. Unfortunately, until [A Ruleset with Metadata Restrictions on Commit Messages should not block Squash Merge Pull Requests unless the sqash commit message itself violates the rule · community · Discussion #108531](https://github.com/orgs/community/discussions/108531) is fixed, this restriction also holds for ALL commit messages to be squash merged. You can easily squash though locally - based on your IDE - e.g. through [Edit Git project history - Squash commits | PyCharm Documentation](https://www.jetbrains.com/help/pycharm/edit-project-history.html#squash-commits) or [Squashing commits in GitHub Desktop - GitHub Docs](https://docs.github.com/en/desktop/managing-commits/squashing-commits-in-github-desktop).**  

Note: PRs submitted from forks external to this organization do not automatically trigger required workflows to run. Approval granted based on [Approving workflow runs from public forks - GitHub Docs](https://docs.github.com/en/actions/managing-workflow-runs/approving-workflow-runs-from-public-forks#approving-workflow-runs-on-a-pull-request-from-a-public-fork).
Rationale: [Keeping your GitHub Actions and workflows secure Part 1: Preventing pwn requests | GitHub Security Lab](https://securitylab.github.com/research/github-actions-preventing-pwn-requests/)


# Attribution
This template was inspired by <https://github.com/nayafia/contributing-template>.
