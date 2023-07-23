# Copyright 2023 Erickrus. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#!pip install -q sqlfluff>=2.1.3
#!pip install -q sqlparse>=0.4.4
import json
import re
import sqlfluff
import sqlparse

@staticmethod
def extract_sql_command(
    text: str,
    dialect: str = 'ansi',
    return_all: bool = False
    ) -> str:
    # concatenate res from sqlfluff.parse
    def concat_dict(dict_data: dict) -> str:
        res = ""
        for value in dict_data.values():
            if isinstance(value, dict):
                res += concat_dict(value)
            elif isinstance(value, list) or isinstance(value, tuple):
                for i in range(len(value)):
                    res += concat_dict(value[i])
            else:
                res += str(value)
        return res

    # regex to find valid check positions
    def get_check_positions(text: str) -> list[int]:
        sql_keywords = [
            'WITH', # CTE
            'SELECT', 'INSERT', 'DELETE', 'UPDATE', 'UPSERT', 'REPLACE', 'MERGE', 'COMMIT', 'ROLLBACK', 'START', # DML
            'DROP', 'CREATE', 'ALTER', # DDL
        ]
        keyword_positions = []
        for keyword in sql_keywords:
            sql_pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            for match in sql_pattern.finditer(text):
                keyword_positions.append(match.start())
        keyword_positions = sorted(keyword_positions)
        return keyword_positions

    res = []
    extract_pos = 0
    token_types = sqlparse.tokens._TokenType()
    error_line_pattern = r"Line (\d+), Position (\d+): (.*)"
    keyword_positions = get_check_positions(text)

    while extract_pos < len(text) - 2:
        if extract_pos in keyword_positions:
            # check the text character by character
            current_statement = text[extract_pos:]
            parsed = sqlparse.parse(current_statement)[0]
            # filter based on the token type only allow DML, DDL, CTE to continue
            if parsed.tokens[0].ttype in (token_types.Keyword.DML, token_types.Keyword.DDL, token_types.Keyword.CTE):
                # try to use sqlfluff to check the syntax
                candidate_sql = ""
                current_lines = current_statement.splitlines()
                try:
                    sqlfluff.parse(current_statement, dialect=dialect)
                    candidate_sql = current_statement
                except sqlfluff.api.simple.APIParsingError as e:
                    # find out first violation's line and position
                    # parse the error message
                    msg_lines = str(e.msg).split("\n")
                    for j in range(len(msg_lines)):
                        if re.search(error_line_pattern, msg_lines[j]):
                            line_no, position = str(msg_lines[j]).split(":")[0].split(",")
                            line_no, position = int(line_no.strip().split(' ')[1]), int(position.strip().split(' ')[1])
                            # extract the candidate sql
                            for k in range(line_no-1):
                                candidate_sql += current_lines[k] + "\n"
                            candidate_sql += current_lines[line_no-1][:position-1]
                            break
                # for shorter statement, use length filter
                try:
                    parsed_res = sqlfluff.parse(candidate_sql, dialect=dialect)
                    # retrieve the first sql, sometimes it returns multiple sql separated by ;
                    if isinstance(parsed_res['file'], list):
                        candidate_sql = concat_dict(parsed_res['file'][0])
                    parsed = sqlparse.parse(candidate_sql)[0]
                    if len(candidate_sql.split()) <= 3 and parsed.tokens[0].ttype in (token_types.Keyword.DML):
                        pass
                    elif len(candidate_sql.split()) <= 2:
                        pass
                    else:
                        extract_pos += len(candidate_sql) - 1
                        res.append(candidate_sql)
                except Exception as e:
                    pass
        extract_pos += 1
    if return_all:
        return res # return all valid
    if len(res) == 0:
        return ""
    else:
        return max(res, key=len) # return the longest

@staticmethod
def extract_json_command(text: str, return_all: bool = False) -> str:
    res = []
    extract_pos = 0
    error_line_pattern = r".*: line (\d+) column (\d+) (.*)"
    
    while extract_pos < len(text) - 2:
        # check the text character by character
        if text[extract_pos] in ['{', '[']:
            current_text = text[extract_pos:]
            current_statement = text[extract_pos:]
             # try to use json.loads to check the syntax
            try:
                candidate_json = ""
                current_lines = current_statement.splitlines()
                json.loads(current_text)
            except json.decoder.JSONDecodeError as e:
                # parse the error message
                msg_lines = str(e).split("\n")
                for j in range(len(msg_lines)):
                    if re.search(error_line_pattern, msg_lines[j]):
                        line_and_column = str(msg_lines[j]).split(":")[1].split(' ')
                        line_no, position = line_and_column[2], line_and_column[4]
                        line_no, position = int(line_no.strip()), int(position.strip())
                        if line_no == 1 and position == 1:
                            pass
                        else:
                            # extract the candidate json
                            for k in range(line_no-1):
                                candidate_json += current_lines[k] + "\n"
                            candidate_json += current_lines[line_no-1][:position-1]
                            if len(candidate_json.strip()) == 0:
                                pass
                            else:
                                try:
                                    json.loads(candidate_json)
                                    extract_pos += len(candidate_json) - 1
                                    res.append(candidate_json)
                                except Exception as e:
                                    pass
        extract_pos += 1
    if return_all:
        return res # return all valid
    if len(res) == 0:
        return ""
    else:
        return max(res, key=len) # return the longest
