class MockFileDataBase:
    def delete(self, content_base_uuid: str, content_base_file_uuid: str, filename: str):
        return {"status": 200, "data": ""}
