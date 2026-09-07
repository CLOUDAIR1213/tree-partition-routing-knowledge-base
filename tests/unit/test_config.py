from app.core.config import Settings


def test_settings_parses_csv_collection_values_from_env_file(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ALLOWED_FILE_TYPES=pdf,docx,txt,md\n"
        "CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.allowed_file_types == ("pdf", "docx", "txt", "md")
    assert settings.cors_origins == (
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    )
