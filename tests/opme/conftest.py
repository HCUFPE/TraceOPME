# As suítes desta pasta são scripts (rodam no import, com banco temporário
# próprio) e são executadas em processos separados por tests/test_opme_suite.py.
# Não deixar o pytest importá-las no mesmo processo: compartilhariam o banco.
collect_ignore_glob = ["test_*.py"]
