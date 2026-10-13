"""Share browser state within an account and isolate it between accounts."""

from ultralight_py import Runtime


def main():
    with Runtime(cache_path="./browser-data") as runtime:
        account_a = runtime.get_or_create_session("account-a", persistent=True)
        account_b = runtime.create_session("account-b", persistent=True)
        with (
            runtime.create_view(800, 600, session=account_a) as login_view,
            runtime.create_view(800, 600, session=account_a) as task_view,
            runtime.create_view(800, 600, session=account_b) as other_view,
        ):
            login_view.load_html("<body>Account A login", url="http://example.test/")
            task_view.load_html("<body>Account A task", url="http://example.test/")
            other_view.load_html("<body>Account B", url="http://example.test/")
            runtime.update()
            print(account_a.name, account_a.disk_path)
            print(account_b.name, account_b.disk_path)
        account_a.close()
        account_b.close()


if __name__ == "__main__":
    main()
