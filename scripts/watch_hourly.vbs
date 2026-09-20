Set sh = CreateObject("Wscript.Shell")
sh.CurrentDirectory = "C:\Users\ravir\ConsultingCompanyAutomation"
sh.Run """C:\Python313\python.exe"" -u ""C:\Users\ravir\ConsultingCompanyAutomation\scripts\watch_jobs.py"" --once --mail", 0, True
