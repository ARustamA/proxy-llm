"""Главное окно приложения LLM Proxy Server GUI."""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
import subprocess
import threading
import queue
import time

from src.models import AppConfig, Provider, RoutingRule, Group, PROVIDER_TYPES
from src.utils.config import (
    save_config, load_config, get_default_config_path, 
    validate_provider, validate_routing_rule, validate_group,
    create_default_config, get_env_template, config_to_toml
)
from src.utils.tokens import (
    count_tokens, count_messages_tokens, estimate_cost,
    ENCODINGS, get_available_models
)
from src.utils.test_connection import test_provider_sync
from src.utils.test_universal import test_api_simple as universal_tester


def install_clipboard_shortcuts(root: tk.Tk):
    """Ctrl+C/V/X/A в полях ввода при русской раскладке клавиатуры и Caps Lock."""
    pairs = (
        (("A", "Cyrillic_ef", "Cyrillic_EF"), "<<SelectAll>>"),
        (("C", "Cyrillic_es", "Cyrillic_ES"), "<<Copy>>"),
        (("V", "Cyrillic_ve", "Cyrillic_VE"), "<<Paste>>"),
        (("X", "Cyrillic_che", "Cyrillic_CHE"), "<<Cut>>"),
    )

    def make_handler(virtual):
        def handler(event):
            try:
                event.widget.event_generate(virtual)
            except tk.TclError:
                pass
            return "break"
        return handler

    for keysyms, virtual in pairs:
        for keysym in keysyms:
            root.bind_all(f"<Control-KeyPress-{keysym}>", make_handler(virtual))


class ProxyServer:
    """Управление процессом llm-proxy-server."""

    def __init__(self):
        self.process = None
        self.log_queue = queue.Queue()
        self._running = False
        self._stop_flag = threading.Event()
        self._log_callbacks = []

    def add_log_callback(self, callback):
        self._log_callbacks.append(callback)

    @property
    def is_running(self):
        return self._running and self.process is not None and self.process.poll() is None

    def _read_output(self):
        try:
            for line in iter(self.process.stdout.readline, ""):
                if self._stop_flag.is_set():
                    break
                line = line.strip()
                if line:
                    self.log_queue.put(line)
                    for cb in self._log_callbacks:
                        try:
                            cb(line)
                        except Exception:
                            pass
        except (ValueError, OSError):
            pass
        finally:
            self._running = False

    def write_config(self, app_config):
        toml = config_to_toml(app_config)
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy_config.toml")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(toml)
        self._port = app_config.server.port
        return config_path

    def start(self, app_config, debug=False):
        self.stop()
        self.force_kill_port()
        config_path = self.write_config(app_config)
        self._stop_flag.clear()
        self._running = True

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        cmd = ["llm-proxy-server", "--config", config_path]
        if debug:
            cmd.append("--debug")
        project_root = os.path.dirname(os.path.abspath(__file__))
        env = os.environ.copy()
        python_path = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join(
            path for path in (project_root, python_path) if path
        )
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creationflags,
                cwd=project_root,
                env=env,
            )
            threading.Thread(target=self._read_output, daemon=True).start()
        except FileNotFoundError:
            self._running = False
            self.process = None
            print("llm-proxy-server not found. Install it or check PATH.")

    def force_kill_port(self):
        port = self.get_port()
        try:
            import re
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "LISTENING" not in line:
                    continue
                parts = re.split(r"\s+", line.strip())
                if len(parts) >= 5 and parts[0].startswith("TCP") and parts[1].endswith(f":{port}"):
                    pid = parts[-1]
                    subprocess.run(["taskkill", "/f", "/pid", pid], capture_output=True)
                    return f"killed PID {pid} on port {port}"
        except Exception:
            pass
        return None

    def stop(self):
        self._stop_flag.set()
        self._running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    self.process.kill()
                    self.process.wait(timeout=2)
                except Exception:
                    pass
            finally:
                self.process = None

    def restart(self, app_config, debug=False):
        self.start(app_config, debug=debug)

    def get_port(self):
        return getattr(self, "_port", 8000)


# Override test for custom/minimax to give detailed
original_test_connection = test_provider_sync


def test_with_universal(provider, model=None):
    if provider.api_type in ("minimax", "custom"):
        return universal_tester(provider.api_key, provider.api_base, model or provider.model)
    return original_test_connection(provider, model or provider.model)


class LLMGuiApp:
    """Главное приложение GUI."""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("LLM Proxy Server GUI")
        self.root.geometry("1000x700")
        self.root.minsize(900, 650)

        install_clipboard_shortcuts(root)

        self.server = ProxyServer()
        self.server.add_log_callback(self._on_server_log)

        self.debug_mode = tk.BooleanVar(value=False)

        # Текущая конфигурация
        self.config: AppConfig = create_default_config()
        self.config_path: str = get_default_config_path()

        # Настройка стилей
        self.setup_styles()

        # Создание UI
        self.create_ui()

        # Загрузка конфигурации
        self.load_current_config()

        # Авто-запуск сервера
        self.root.after(500, self._auto_start_server)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
    def setup_styles(self):
        """Настроить стили."""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Цветовая схема
        style.configure('.', background='#1E1E2E', foreground='#F8FAFC')
        style.configure('TFrame', background='#1E1E2E')
        style.configure('TLabel', background='#1E1E2E', foreground='#F8FAFC')
        style.configure('TButton', background='#2D2D3F', foreground='#F8FAFC', 
                       borderwidth=1, relief='flat')
        style.map('TButton', background=[('active', '#3D3D5C')])
        style.configure('TEntry', fieldbackground='#2D2D3F', foreground='#F8FAFC',
                       borderwidth=1, relief='solid')
        style.configure('TCheckbutton', background='#1E1E2E', foreground='#F8FAFC')
        style.map('TCheckbutton',
                 background=[('active', '#1E1E2E'), ('pressed', '#1E1E2E')],
                 foreground=[('active', '#F8FAFC'), ('pressed', '#F8FAFC')])
        style.configure('TRadiobutton', background='#1E1E2E', foreground='#F8FAFC')
        style.configure('TNotebook', background='#1E1E2E', tabposition='n')
        style.configure('TNotebook.Tab', background='#2D2D3F', foreground='#F8FAFC',
                       padding=[10, 5])
        style.map('TNotebook.Tab', background=[('selected', '#7C3AED')])
        
        # Treeview
        style.configure('Treeview', background='#2D2D3F', foreground='#F8FAFC',
                       fieldbackground='#2D2D3F', rowheight=28)
        style.configure('Treeview.Heading', background='#3D3D5C', foreground='#F8FAFC',
                       font=('Segoe UI', 10, 'bold'))
        style.map('Treeview', background=[('selected', '#7C3AED')])
        style.map('Treeview.Heading',
                 background=[('active', '#4D4D6C')],
                 foreground=[('active', '#F8FAFC')])

        # Combobox
        style.configure('TCombobox', fieldbackground='#2D2D3F', foreground='#F8FAFC',
                       background='#2D2D3F', arrowcolor='#F8FAFC',
                       selectbackground='#7C3AED', selectforeground='#F8FAFC',
                       borderwidth=1, relief='solid')
        style.map('TCombobox',
                 fieldbackground=[('readonly', '#2D2D3F')],
                 foreground=[('readonly', '#F8FAFC')],
                 background=[('active', '#3D3D5C'), ('pressed', '#3D3D5C')],
                 arrowcolor=[('active', '#7C3AED'), ('pressed', '#7C3AED')])
        # Стилизация выпадающего списка Combobox
        self.root.option_add('*TCombobox*Listbox.background', '#2D2D3F')
        self.root.option_add('*TCombobox*Listbox.foreground', '#F8FAFC')
        self.root.option_add('*TCombobox*Listbox.selectBackground', '#7C3AED')
        self.root.option_add('*TCombobox*Listbox.selectForeground', '#F8FAFC')

        # LabelFrame
        style.configure('TLabelframe', background='#1E1E2E', foreground='#F8FAFC')
        style.configure('TLabelframe.Label', background='#1E1E2E', foreground='#F8FAFC',
                       font=('Segoe UI', 10, 'bold'))

        # Scrollbar
        style.configure('TScrollbar', background='#2D2D3F', troughcolor='#1E1E2E',
                       arrowcolor='#F8FAFC', bordercolor='#2D2D3F', relief='flat')
        style.map('TScrollbar',
                 background=[('active', '#3D3D5C'), ('pressed', '#7C3AED')],
                 arrowcolor=[('active', '#7C3AED'), ('pressed', '#FFFFFF')])
        style.configure('Vertical.TScrollbar', background='#2D2D3F', troughcolor='#1E1E2E',
                       arrowcolor='#F8FAFC')
        style.map('Vertical.TScrollbar',
                 background=[('active', '#3D3D5C'), ('pressed', '#7C3AED')])

        # Toplevel (диалоговые окна)
        style.configure('Toplevel', background='#1E1E2E')
        # Глобальный фон для всех окон
        self.root.option_add('*Toplevel.background', '#1E1E2E')
        self.root.option_add('*Dialog.background', '#1E1E2E')
        self.root.option_add('*Menu.background', '#2D2D3F')
        self.root.option_add('*Menu.foreground', '#F8FAFC')
        self.root.option_add('*Menu.activeBackground', '#3D3D5C')
        self.root.option_add('*Menu.activeForeground', '#F8FAFC')

        # Separator
        style.configure('TSeparator', background='#3D3D5C')

        # Scrollbar
        style.configure('TScrollbar', background='#2D2D3F', troughcolor='#1E1E2E',
                       arrowcolor='#F8FAFC', borderwidth=0, relief='flat')
        style.map('TScrollbar',
                 background=[('active', '#3D3D5C'), ('pressed', '#3D3D5C')],
                 arrowcolor=[('active', '#7C3AED'), ('pressed', '#7C3AED')])
        
    def create_ui(self):
        """Создать пользовательский интерфейс."""
        # Меню
        self.create_menu()
        
        # main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        # Notbook (вкладки)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Создание вкладок
        self.tab_connections = self.create_connections_tab()
        self.tab_routing = self.create_routing_tab()
        self.tab_groups = self.create_groups_tab()
        self.tab_tokens = self.create_tokens_tab()
        self.tab_settings = self.create_settings_tab()
        self.tab_server = self.create_server_tab()

        self.notebook.add(self.tab_connections, text="Провайдеры")
        self.notebook.add(self.tab_routing, text="Маршрутизация")
        self.notebook.add(self.tab_groups, text="Группы")
        self.notebook.add(self.tab_tokens, text="Токены")
        self.notebook.add(self.tab_settings, text="Настройки")
        self.notebook.add(self.tab_server, text="Сервер")
        
        # Status bar
        self.create_status_bar()
        
    def create_menu(self):
        """Создать меню."""
        menubar = tk.Menu(self.root, bg='#2D2D3F', fg='#F8FAFC')
        self.root.config(menu=menubar)
        
        # Файл
        file_menu = tk.Menu(menubar, bg='#2D2D3F', fg='#F8FAFC', tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Новый", command=self.new_config)
        file_menu.add_command(label="Открыть...", command=self.open_config)
        file_menu.add_command(label="Сохранить", command=self.save_config_action)
        file_menu.add_command(label="Сохранить как...", command=self.save_config_as)
        file_menu.add_separator()
        file_menu.add_command(label="Экспорт в TOML...", command=self.export_toml)
        file_menu.add_command(label="Создать .env.template", command=self.create_env_template)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.root.quit)
        
        # Справка
        help_menu = tk.Menu(menubar, bg='#2D2D3F', fg='#F8FAFC', tearoff=0)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="О программе", command=self.show_about)
        
    def create_status_bar(self):
        """Создать статус бар."""
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        ttk.Label(status_frame, text="Конфигурация:").pack(side=tk.LEFT, padx=10, pady=5)
        
        self.status_config_label = ttk.Label(status_frame, text=self.config_path)
        self.status_config_label.pack(side=tk.LEFT)
        
        self.status_label = ttk.Label(status_frame, text="Готово", foreground='#10B981')
        self.status_label.pack(side=tk.RIGHT, padx=10, pady=5)
        
    # ==================== Connections Tab ====================
    def create_connections_tab(self) -> ttk.Frame:
        """Создать вкладку провайдеров."""
        frame = ttk.Frame(self.notebook)
        
        # Toolbar
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(toolbar, text="Добавить", command=self.add_provider).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Редактировать", command=self.edit_provider).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Удалить", command=self.delete_provider).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)
        ttk.Button(toolbar, text="Тест соединения", command=self.test_connection).pack(side=tk.LEFT, padx=2)
        
        # Treeview
        columns = ("name", "api_type", "api_base", "model", "api_key", "enabled")
        self.providers_tree = ttk.Treeview(frame, columns=columns, show='headings')
        
        self.providers_tree.heading("name", text="Имя")
        self.providers_tree.heading("api_type", text="Тип API")
        self.providers_tree.heading("api_base", text="API Base")
        self.providers_tree.heading("model", text="Модель")
        self.providers_tree.heading("api_key", text="API Key")
        self.providers_tree.heading("enabled", text="Включён")
        
        self.providers_tree.column("name", width=100)
        self.providers_tree.column("api_type", width=100)
        self.providers_tree.column("api_base", width=200)
        self.providers_tree.column("model", width=120)
        self.providers_tree.column("api_key", width=150)
        self.providers_tree.column("enabled", width=60)
        
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.providers_tree.yview)
        self.providers_tree.configure(yscrollcommand=scrollbar.set)
        
        self.providers_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5, padx=(0, 10))
        
        return frame
    
    def refresh_providers_tree(self):
        """Обновить дерево провайдеров."""
        self.providers_tree.delete(*self.providers_tree.get_children())
        
        for provider in self.config.connections:
            # Маскируем API ключ
            display_key = provider.api_key
            if len(display_key) > 20 and not display_key.startswith("env:"):
                display_key = display_key[:20] + "..."
            
            self.providers_tree.insert("", tk.END, values=(
                provider.name,
                provider.api_type,
                provider.api_base or "",
                provider.model or "",
                display_key,
                "Да" if provider.enabled else "Нет"
            ), tags=(provider.name,))
    
    def add_provider(self):
        """Добавить провайдера."""
        dialog = ProviderDialog(self.root, title="Добавить провайдера")
        if dialog.provider:
            # Проверяем на дубликаты
            for p in self.config.connections:
                if p.name == dialog.provider.name:
                    messagebox.showerror("Ошибка", f"Провайдер '{dialog.provider.name}' уже существует")
                    return
            
            self.config.connections.append(dialog.provider)
            self.refresh_providers_tree()
            self.set_status(f"Добавлен провайдер: {dialog.provider.name}")
            self._on_config_changed()

    def edit_provider(self):
        """Редактировать провайдера."""
        selection = self.providers_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите провайдера для редактирования")
            return
        
        item = self.providers_tree.item(selection[0])
        name = item['values'][0]
        
        # Находим провайдера
        provider = None
        for p in self.config.connections:
            if p.name == name:
                provider = p
                break
        
        if provider:
            dialog = ProviderDialog(self.root, title="Редактировать провайдера", provider=provider)
            if dialog.provider:
                new_name = dialog.provider.name
                if new_name != provider.name and any(p.name == new_name for p in self.config.connections):
                    messagebox.showerror("Ошибка", f"Провайдер '{new_name}' уже существует")
                    return
                provider.name = new_name
                provider.api_type = dialog.provider.api_type
                provider.api_base = dialog.provider.api_base
                provider.api_key = dialog.provider.api_key
                provider.model = dialog.provider.model
                provider.enabled = dialog.provider.enabled
                provider.reasoning_effort = dialog.provider.reasoning_effort
                provider.thinking = dialog.provider.thinking
                self.refresh_providers_tree()
                self.set_status(f"Обновлён провайдер: {provider.name}")
                self._on_config_changed()

    def delete_provider(self):
        """Удалить провайдера."""
        selection = self.providers_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите провайдера для удаления")
            return
        
        item = self.providers_tree.item(selection[0])
        name = item['values'][0]
        
        if messagebox.askyesno("Подтверждение", f"Удалить провайдера '{name}'?"):
            self.config.connections = [p for p in self.config.connections if p.name != name]
            self.refresh_providers_tree()
            self.set_status(f"Удалён провайдер: {name}")
            self._on_config_changed()

    def test_connection(self):
        """Тест соединения."""
        selection = self.providers_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите провайдера для теста")
            return
        
        item = self.providers_tree.item(selection[0])
        name = item['values'][0]
        
        # Find provider
        provider = None
        for p in self.config.connections:
            if p.name == name:
                provider = p
                break
        
        if provider:
            self.set_status(f"Тестирование {name}...")
            success, message = test_with_universal(provider, provider.model)
            
            if success:
                messagebox.showinfo("Тест", f"✓ {name}: {message}")
                self.set_status(f"Тест {name} успешен")
            else:
                messagebox.showerror("Тест", f"✗ {name}: {message}")
                self.set_status(f"Тест {name} неуспешен")
    
    # ==================== Routing Tab ====================
    def create_routing_tab(self) -> ttk.Frame:
        """Создать вкладку маршрутизации."""
        frame = ttk.Frame(self.notebook)
        
        # Toolbar
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(toolbar, text="Добавить маршрут", command=self.add_route).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Редактировать", command=self.edit_route).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Удалить", command=self.delete_route).pack(side=tk.LEFT, padx=2)
        
        # Treeview
        columns = ("model_pattern", "connection", "model_name")
        self.routing_tree = ttk.Treeview(frame, columns=columns, show='headings')
        
        self.routing_tree.heading("model_pattern", text="Паттерн модели")
        self.routing_tree.heading("connection", text="Подключение")
        self.routing_tree.heading("model_name", text="Модель")
        
        self.routing_tree.column("model_pattern", width=200)
        self.routing_tree.column("connection", width=200)
        self.routing_tree.column("model_name", width=250)
        
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.routing_tree.yview)
        self.routing_tree.configure(yscrollcommand=scrollbar.set)
        
        self.routing_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5, padx=(0, 10))
        
        return frame
    
    def refresh_routing_tree(self):
        """Обновить дерево маршрутов."""
        self.routing_tree.delete(*self.routing_tree.get_children())
        
        for route in self.config.routing:
            self.routing_tree.insert("", tk.END, values=(
                route.model_pattern,
                route.connection,
                route.target_model
            ))
    
    def add_route(self):
        """Добавить маршрут."""
        dialog = RoutingDialog(self.root, self.config.connections)
        if dialog.rule:
            self.config.routing.append(dialog.rule)
            self.refresh_routing_tree()
            self.set_status(f"Добавлен маршрут: {dialog.rule.model_pattern}")
            self._on_config_changed()

    def edit_route(self):
        """Редактировать маршрут."""
        selection = self.routing_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите маршрут для редактирования")
            return
        
        item = self.routing_tree.item(selection[0])
        pattern = item['values'][0]
        
        route = None
        for r in self.config.routing:
            if r.model_pattern == pattern:
                route = r
                break
        
        if route:
            dialog = RoutingDialog(self.root, self.config.connections, route)
            if dialog.rule:
                route.model_pattern = dialog.rule.model_pattern
                route.connection = dialog.rule.connection
                route.target_model = dialog.rule.target_model
                self.refresh_routing_tree()
                self.set_status(f"Обновлён маршрут: {route.model_pattern}")
                self._on_config_changed()

    def delete_route(self):
        """Удалить маршрут."""
        selection = self.routing_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите маршрут для удаления")
            return
        
        item = self.routing_tree.item(selection[0])
        pattern = item['values'][0]
        
        if messagebox.askyesno("Подтверждение", f"Удалить маршрут '{pattern}'?"):
            self.config.routing = [r for r in self.config.routing if r.model_pattern != pattern]
            self.refresh_routing_tree()
            self.set_status(f"Удалён маршрут: {pattern}")
            self._on_config_changed()

    # ==================== Groups Tab ====================
    def create_groups_tab(self) -> ttk.Frame:
        """Создать вкладку групп."""
        frame = ttk.Frame(self.notebook)
        
        # Toolbar
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(toolbar, text="Добавить группу", command=self.add_group).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Редактировать", command=self.edit_group).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Удалить", command=self.delete_group).pack(side=tk.LEFT, padx=2)
        
        # Treeview
        columns = ("name", "api_keys_count", "allowed_connections")
        self.groups_tree = ttk.Treeview(frame, columns=columns, show='headings')
        
        self.groups_tree.heading("name", text="Имя группы")
        self.groups_tree.heading("api_keys_count", text="Кол-во ключей")
        self.groups_tree.heading("allowed_connections", text="Разрешённые подключения")
        
        self.groups_tree.column("name", width=200)
        self.groups_tree.column("api_keys_count", width=120)
        self.groups_tree.column("allowed_connections", width=300)
        
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.groups_tree.yview)
        self.groups_tree.configure(yscrollcommand=scrollbar.set)
        
        self.groups_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5, padx=(0, 10))
        
        return frame
    
    def refresh_groups_tree(self):
        """Обновить дерево групп."""
        self.groups_tree.delete(*self.groups_tree.get_children())
        
        for group in self.config.groups:
            self.groups_tree.insert("", tk.END, values=(
                group.name,
                len(group.api_keys),
                group.allowed_connections
            ))
    
    def add_group(self):
        """Добавить группу."""
        dialog = GroupDialog(self.root, title="Добавить группу")
        if dialog.group:
            self.config.groups.append(dialog.group)
            self.refresh_groups_tree()
            self.set_status(f"Добавлена группа: {dialog.group.name}")
            self._on_config_changed()

    def edit_group(self):
        """Редактировать группу."""
        selection = self.groups_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите группу для редактирования")
            return
        
        item = self.groups_tree.item(selection[0])
        name = item['values'][0]
        
        group = None
        for g in self.config.groups:
            if g.name == name:
                group = g
                break
        
        if group:
            dialog = GroupDialog(self.root, title="Редактировать группу", group=group)
            if dialog.group:
                group.name = dialog.group.name
                group.api_keys = dialog.group.api_keys
                group.allowed_connections = dialog.group.allowed_connections
                self.refresh_groups_tree()
                self.set_status(f"Обновлена группа: {group.name}")
                self._on_config_changed()

    def delete_group(self):
        """Удалить группу."""
        selection = self.groups_tree.selection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите группу для удаления")
            return
        
        item = self.groups_tree.item(selection[0])
        name = item['values'][0]
        
        if messagebox.askyesno("Подтверждение", f"Удалить группу '{name}'?"):
            self.config.groups = [g for g in self.config.groups if g.name != name]
            self.refresh_groups_tree()
            self.set_status(f"Удалена группа: {name}")
            self._on_config_changed()

    # ==================== Tokens Tab ====================
    def create_tokens_tab(self) -> ttk.Frame:
        """Создать вкладку токенов."""
        frame = ttk.Frame(self.notebook)
        
        # Input area
        input_frame = ttk.LabelFrame(frame, text="Входной текст", padding=10)
        input_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.token_text = tk.Text(input_frame, height=10, wrap=tk.WORD, 
                               bg='#2D2D3F', fg='#F8FAFC', insertbackground='#F8FAFC')
        self.token_text.pack(fill=tk.BOTH, expand=True)
        
        # Controls
        controls_frame = ttk.Frame(frame)
        controls_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(controls_frame, text="Кодировка:").pack(side=tk.LEFT, padx=5)
        
        self.encoding_var = tk.StringVar(value="cl100k_base")
        self.encoding_combo = ttk.Combobox(controls_frame, textvariable=self.encoding_var, 
                                      values=list(ENCODINGS.keys()), state='readonly', width=15)
        self.encoding_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(controls_frame, text="Модель:").pack(side=tk.LEFT, padx=15)
        
        self.model_var = tk.StringVar(value="gpt-3.5-turbo")
        self.model_combo = ttk.Combobox(controls_frame, textvariable=self.model_var, 
                                     values=["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", 
                                            "gpt-4o", "gpt-4o-mini"], state='readonly', width=15)
        self.model_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(controls_frame, text="Подсчитать токены", command=self.count_token_action).pack(side=tk.LEFT, padx=20)
        
        # Results
        results_frame = ttk.LabelFrame(frame, text="Результаты", padding=10)
        results_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.tokens_result_label = ttk.Label(results_frame, text="Токенов: 0")
        self.tokens_result_label.pack(side=tk.LEFT, padx=20)
        
        self.cost_result_label = ttk.Label(results_frame, text="Примерная стоимость: $0.00")
        self.cost_result_label.pack(side=tk.LEFT, padx=20)
        
        return frame
    
    def update_encoding_info(self):
        """Обновить информацию о кодировке."""
        enc = self.encoding_var.get()
        models = get_available_models(enc)
        self.model_combo['values'] = models
        if models:
            self.model_var.set(models[0])
    
    def count_token_action(self):
        """Подсчитать токены."""
        text = self.token_text.get("1.0", tk.END).strip()
        if not text:
            self.tokens_result_label.config(text="Токенов: 0")
            self.cost_result_label.config(text="Примерная стоимость: $0.00")
            return
        
        encoding = self.encoding_var.get()
        model = self.model_var.get()
        
        tokens = count_tokens(text, encoding)
        cost = estimate_cost(tokens, model, encoding)
        
        self.tokens_result_label.config(text=f"Токенов: {tokens}")
        self.cost_result_label.config(text=f"Примерная стоимость: ${cost:.4f}")
    
    # ==================== Settings Tab ====================
    def create_settings_tab(self) -> ttk.Frame:
        """Создать вкладку настроек."""
        frame = ttk.Frame(self.notebook)
        
        # Server settings
        server_frame = ttk.LabelFrame(frame, text="Настройки сервера", padding=10)
        server_frame.pack(fill=tk.X, padx=10, pady=10)
        
        grid = ttk.Frame(server_frame)
        grid.pack(fill=tk.X)
        
        ttk.Label(grid, text="Host:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.host_entry = ttk.Entry(grid, width=30)
        self.host_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        self.host_entry.insert(0, self.config.server.host)
        self.host_entry.bind("<FocusOut>", self.save_settings)

        ttk.Label(grid, text="Port:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        self.port_entry = ttk.Entry(grid, width=10)
        self.port_entry.grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        self.port_entry.insert(0, str(self.config.server.port))
        self.port_entry.bind("<FocusOut>", self.save_settings)

        self.autoreload_var = tk.BooleanVar(value=self.config.server.dev_autoreload)
        ttk.Checkbutton(grid, text="Автоперезагрузка (dev)", variable=self.autoreload_var,
                        command=self.save_settings).grid(
            row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        # Model listing
        ttk.Label(grid, text="Mode listing:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        self.listing_combo = ttk.Combobox(grid, values=["as_is", "ignore_wildcards", "expand_wildcards"],
                                     state='readonly', width=15)
        self.listing_combo.grid(row=1, column=3, sticky=tk.W, padx=5, pady=5)
        self.listing_combo.set(self.config.listing_mode)
        self.listing_combo.bind("<<ComboboxSelected>>", self.save_settings)
        
        # Save button
        ttk.Button(server_frame, text="Сохранить настройки", command=self.save_settings).pack(pady=10)
        
        # Config export
        export_frame = ttk.LabelFrame(frame, text="Экспорт конфигурации", padding=10)
        export_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(export_frame, text="Экспорт в TOML", command=self.export_toml).pack(side=tk.LEFT, padx=5)
        
        return frame
    
    def create_server_tab(self) -> ttk.Frame:
        frame = ttk.Frame(self.notebook)

        # Controls
        ctrl_frame = ttk.LabelFrame(frame, text="Управление сервером", padding=10)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=10)

        buttons = ttk.Frame(ctrl_frame)
        buttons.pack(fill=tk.X)

        ttk.Button(buttons, text="Старт", command=self._server_start).pack(side=tk.LEFT, padx=2)
        ttk.Button(buttons, text="Стоп", command=self._server_stop).pack(side=tk.LEFT, padx=2)
        ttk.Button(buttons, text="Рестарт", command=self._server_restart).pack(side=tk.LEFT, padx=2)
        ttk.Button(buttons, text="🔥 Форс", command=self._server_force_restart).pack(side=tk.LEFT, padx=2)

        ttk.Separator(buttons, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=8, fill=tk.Y)
        ttk.Checkbutton(buttons, text="Debug", variable=self.debug_mode,
                        command=self._toggle_debug).pack(side=tk.LEFT, padx=2)

        self.server_status_var = tk.StringVar(value="Статус: остановлен")
        self.server_status_label = ttk.Label(buttons, textvariable=self.server_status_var, foreground="#94A3B8")
        self.server_status_label.pack(side=tk.LEFT, padx=20)

        self.server_port_var = tk.StringVar(value="Порт: 8000")
        ttk.Label(buttons, textvariable=self.server_port_var, foreground="#94A3B8").pack(side=tk.LEFT, padx=5)

        # Logs
        log_frame = ttk.LabelFrame(frame, text="Логи сервера", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.log_text = tk.Text(log_frame, wrap=tk.WORD, bg="#111118", fg="#F8FAFC",
                                 font=("Consolas", 10), state=tk.DISABLED, height=20)

        self.log_text.bind("<Button-3>", self._log_context_menu)
        self._setup_text_clipboard(self.log_text)

        self.log_text.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(self.log_text, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        clear_btn = ttk.Button(log_frame, text="Очистить логи", command=self._clear_logs)
        clear_btn.pack(pady=5)

        return frame

    def _setup_text_clipboard(self, widget):
        def copy(event=None):
            try:
                sel = widget.get(tk.SEL_FIRST, tk.SEL_LAST)
                widget.clipboard_clear()
                widget.clipboard_append(sel)
            except tk.TclError:
                pass
            return "break"

        def select_all(event=None):
            widget.tag_add(tk.SEL, "1.0", tk.END)
            widget.mark_set(tk.INSERT, "1.0")
            widget.see(tk.INSERT)
            return "break"

        widget.bind("<Control-c>", copy)
        widget.bind("<Control-C>", copy)
        widget.bind("<Control-Key-c>", copy)
        widget.bind("<Control-Key-C>", copy)
        widget.bind("<Control-a>", select_all)
        widget.bind("<Control-A>", select_all)
        widget.bind("<Control-Key-a>", select_all)
        widget.bind("<Control-Key-A>", select_all)
        widget.bind("<Control-v>", lambda e: "break")
        widget.bind("<Control-V>", lambda e: "break")

    def _log_context_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0, bg="#2D2D3F", fg="#F8FAFC")
        menu.add_command(label="Копировать", command=lambda: self.log_text.event_generate("<<Copy>>"))
        menu.add_command(label="Выделить всё", command=lambda: self._select_all_log())
        menu.add_separator()
        menu.add_command(label="Очистить", command=self._clear_logs)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _select_all_log(self):
        self.log_text.tag_add(tk.SEL, "1.0", tk.END)

    def _server_start(self):
        self._log("Starting server...")
        self.server.start(self.config, debug=self.debug_mode.get())
        self._update_server_status()

    def _server_stop(self):
        self._log("Stopping server...")
        self.server.stop()
        self._update_server_status()

    def _server_restart(self):
        self._log("Restarting server...")
        self.server.restart(self.config, debug=self.debug_mode.get())
        self._update_server_status()

    def _server_force_restart(self):
        self._log("Force restart: killing port and restarting...")
        msg = self.server.force_kill_port()
        if msg:
            self._log(msg)
        self.server.start(self.config, debug=self.debug_mode.get())
        self._update_server_status()

    def _toggle_debug(self):
        if self.server.is_running:
            self._server_restart()

    def _auto_start_server(self):
        self._server_start()
        self._poll_server_status()

    def _update_server_status(self):
        alive = self.server.is_running
        if alive:
            self.server_status_var.set("Статус: работает")
            self.server_status_label.config(foreground="#10B981")
            self.server_port_var.set(f"Порт: {self.server.get_port()}")
        else:
            self.server_status_var.set("Статус: остановлен")
            self.server_status_label.config(foreground="#EF4444")

    def _poll_server_status(self):
        self._update_server_status()
        self._status_timer = self.root.after(3000, self._poll_server_status)

    def _on_server_log(self, line):
        self.root.after(0, self._append_log, line)
        self.root.after(0, self._update_server_status)

    def _append_log(self, line):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _log(self, message):
        self._append_log(f"[GUI] {message}")

    def _clear_logs(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _on_close(self):
        if hasattr(self, "_status_timer"):
            self.root.after_cancel(self._status_timer)
        if hasattr(self, "_apply_config_timer"):
            self.root.after_cancel(self._apply_config_timer)
        save_config(self.config, self.config_path)
        self.server.stop()
        self.root.destroy()

    def save_settings(self, *_):
        """Сохранить настройки."""
        host = self.host_entry.get().strip()
        if not host:
            self.set_status("Ошибка: host не может быть пустым")
            return
        try:
            port = int(self.port_entry.get().strip())
        except ValueError:
            self.set_status("Ошибка: порт должен быть числом")
            return
        if not (1 <= port <= 65535):
            self.set_status("Ошибка: порт должен быть в диапазоне 1-65535")
            return

        new_values = (host, port, self.autoreload_var.get(), self.listing_combo.get())
        old_values = (self.config.server.host, self.config.server.port,
                      self.config.server.dev_autoreload, self.config.listing_mode)
        if new_values == old_values:
            return

        (self.config.server.host, self.config.server.port,
         self.config.server.dev_autoreload, self.config.listing_mode) = new_values

        self.set_status("Настройки сохранены")
        self._on_config_changed()


    # ==================== Actions ====================
    def load_current_config(self):
        """Загрузить текущую конфигурацию."""
        cfg = load_config(self.config_path)
        if cfg:
            self.config = cfg
        
        # Refresh all trees
        self.refresh_providers_tree()
        self.refresh_routing_tree()
        self.refresh_groups_tree()
        self._refresh_settings()
        self.set_status(f"Загружена конфигурация: {self.config_path}")
    
    def new_config(self):
        """Создать новую конфигурацию."""
        if messagebox.askyesno("Новая конфигурация", "Создать новую конфигурацию? Несохранённые изменения будут потеряны."):
            self.config = create_default_config()
            self.config_path = get_default_config_path()
            self.refresh_providers_tree()
            self.refresh_routing_tree()
            self.refresh_groups_tree()
            self._refresh_settings()
            self.set_status("Создана новая конфигурация")
            self._on_config_changed()

    def _refresh_settings(self):
        """Обновить поля вкладки настроек из текущей конфигурации."""
        self.host_entry.delete(0, tk.END)
        self.host_entry.insert(0, self.config.server.host)
        self.port_entry.delete(0, tk.END)
        self.port_entry.insert(0, str(self.config.server.port))
        self.autoreload_var.set(self.config.server.dev_autoreload)
        self.listing_combo.set(self.config.listing_mode)
    
    def open_config(self):
        """Открыть конфигурацию."""
        filename = filedialog.askopenfilename(
            title="Открыть конфигурацию",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            cfg = load_config(filename)
            if cfg:
                self.config = cfg
                self.config_path = filename
                self.load_current_config()
                self.set_status(f"Загружена конфигурация: {filename}")
                self._on_config_changed()
            else:
                messagebox.showerror("Ошибка", "Не удалось загрузить конфигурацию")
    
    def save_config_action(self):
        if save_config(self.config, self.config_path):
            self.set_status(f"Конфигурация сохранена: {self.config_path}")
            self._on_config_changed()
        else:
            messagebox.showerror("Ошибка", "Не удалось сохранить конфигурацию")
    
    def save_config_as(self):
        """Сохранить как."""
        filename = filedialog.asksaveasfilename(
            title="Сохранить конфигурацию как",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            self.config_path = filename
            self.save_config_action()
    
    def export_toml(self):
        """Экспорт в TOML."""
        filename = filedialog.asksaveasfilename(
            title="Экспорт в TOML",
            defaultextension=".toml",
            filetypes=[("TOML files", "*.toml"), ("All files", "*.*")]
        )
        
        if filename:
            toml_content = config_to_toml(self.config)
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(toml_content)
            
            messagebox.showinfo("Экспорт", f"Конфигурация экспортирована в {filename}")
    
    def create_env_template(self):
        """Создать .env.template."""
        template = get_env_template()
        
        with open(".env.template", 'w', encoding='utf-8') as f:
            f.write(template)
        
        messagebox.showinfo("Шаблон", "Создан файл .env.template")
    
    def set_status(self, message: str):
        self.status_label.config(text=message)

    def _on_config_changed(self):
        if hasattr(self, "_apply_config_timer"):
            self.root.after_cancel(self._apply_config_timer)
        self._apply_config_timer = self.root.after(800, self._apply_config)

    def _apply_config(self):
        save_config(self.config, self.config_path)
        if self.server.is_running:
            self.server.restart(self.config, debug=self.debug_mode.get())
            self._log("Server restarted due to config change")
        else:
            self.server.write_config(self.config)
    
    def show_about(self):
        """Показать о программе."""
        messagebox.showinfo("О программе", "LLM Proxy Server GUI v1.0\n\n"
                      "Графическая оболочка для llm-proxy-server\n\n"
                      "Создано с использованием tkinter и tiktoken")


class ProviderDialog:
    """Диалог добавления/редактирования провайдера."""
    
    def __init__(self, parent, title: str, provider: Provider = None):
        self.provider: Provider = None
        
        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.geometry("450x480")
        dialog.transient(parent)
        dialog.grab_set()

        # Form
        form = ttk.Frame(dialog, padding=20)
        form.pack(fill=tk.BOTH, expand=True)

        ttk.Label(form, text="Имя:").grid(row=0, column=0, sticky=tk.W, pady=5)
        name_entry = ttk.Entry(form, width=35)
        name_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(form, text="Тип API:").grid(row=1, column=0, sticky=tk.W, pady=5)
        api_type_var = tk.StringVar(value="open_ai")
        api_type_combo = ttk.Combobox(form, textvariable=api_type_var,
                                   values=[t[0] for t in PROVIDER_TYPES],
                                   state='readonly', width=33)
        api_type_combo.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(form, text="API Base:").grid(row=2, column=0, sticky=tk.W, pady=5)
        api_base_entry = ttk.Entry(form, width=35)
        api_base_entry.grid(row=2, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(form, text="API Key:").grid(row=3, column=0, sticky=tk.W, pady=5)
        api_key_entry = ttk.Entry(form, width=35, show="*")
        api_key_entry.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(form, text="(env:VAR_NAME для переменных)").grid(row=4, column=1, sticky=tk.W)
        
        ttk.Label(form, text="Модель:").grid(row=5, column=0, sticky=tk.W, pady=5)
        model_entry = ttk.Entry(form, width=35)
        model_entry.grid(row=5, column=1, sticky=tk.W, pady=5)

        ttk.Label(form, text="Reasoning Effort:").grid(row=6, column=0, sticky=tk.W, pady=5)
        reasoning_var = tk.StringVar(value="")
        reasoning_combo = ttk.Combobox(form, textvariable=reasoning_var,
                                       values=["", "low", "medium", "high", "max"],
                                       state='readonly', width=33)
        reasoning_combo.grid(row=6, column=1, sticky=tk.W, pady=5)

        ttk.Label(form, text="(DeepSeek thinking, только для open_ai)").grid(row=7, column=1, sticky=tk.W)

        thinking_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="Thinking mode (DeepSeek)", variable=thinking_var).grid(
            row=8, column=0, columnspan=2, sticky=tk.W, pady=5)

        enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text="Включён", variable=enabled_var).grid(
            row=9, column=0, columnspan=2, sticky=tk.W, pady=15)
        
        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        def on_ok():
            api_key = api_key_entry.get().strip()
            if not name_entry.get().strip() or not api_key:
                messagebox.showerror("Ошибка", "Имя и API ключ обязательны")
                return
            
            self.provider = Provider(
                name=name_entry.get().strip(),
                api_type=api_type_var.get(),
                api_base=api_base_entry.get().strip() or None,
                api_key=api_key,
                model=model_entry.get().strip() or None,
                reasoning_effort=reasoning_var.get() or None,
                thinking=thinking_var.get(),
                enabled=enabled_var.get()
            )
            dialog.destroy()
        
        ttk.Button(btn_frame, text="ОК", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Fill if editing
        if provider:
            name_entry.insert(0, provider.name)
            api_type_var.set(provider.api_type)
            api_base_entry.insert(0, provider.api_base or "")
            api_key_entry.insert(0, provider.api_key)
            model_entry.insert(0, provider.model or "")
            reasoning_var.set(provider.reasoning_effort or "")
            thinking_var.set(provider.thinking)
            enabled_var.set(provider.enabled)
        
        dialog.wait_window()


class RoutingDialog:
    """Диалог добавления/редактирования маршрута."""
    
    def __init__(self, parent, connections: list[Provider], route: RoutingRule = None):
        self.rule: RoutingRule = None
        
        dialog = tk.Toplevel(parent)
        dialog.title("Маршрут")
        dialog.geometry("400x250")
        dialog.transient(parent)
        dialog.grab_set()
        
        # Form
        form = ttk.Frame(dialog, padding=20)
        form.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(form, text="Паттерн модели:").grid(row=0, column=0, sticky=tk.W, pady=5)
        pattern_entry = ttk.Entry(form, width=30)
        pattern_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(form, text="(gpt* для всех GPT моделей)").grid(row=1, column=1, sticky=tk.W)
        
        ttk.Label(form, text="Подключение:").grid(row=2, column=0, sticky=tk.W, pady=5)
        conn_names = [c.name for c in connections]
        conn_var = tk.StringVar(value=conn_names[0] if conn_names else "")
        conn_combo = ttk.Combobox(form, textvariable=conn_var, values=conn_names,
                                 state='readonly', width=28)
        conn_combo.grid(row=2, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(form, text="Модель:").grid(row=3, column=0, sticky=tk.W, pady=5)
        model_entry = ttk.Entry(form, width=30)
        model_entry.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        def on_ok():
            pattern = pattern_entry.get().strip()
            conn = conn_var.get()
            model = model_entry.get().strip()
            
            if not pattern or not conn or not model:
                messagebox.showerror("Ошибка", "Все поля обязательны")
                return
            
            self.rule = RoutingRule(
                model_pattern=pattern,
                connection=conn,
                target_model=model
            )
            dialog.destroy()
        
        ttk.Button(btn_frame, text="ОК", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Fill if editing
        if route:
            pattern_entry.insert(0, route.model_pattern)
            conn_var.set(route.connection)
            model_entry.insert(0, route.target_model)
        
        dialog.wait_window()


class GroupDialog:
    """Диалог добавления/редактирования группы."""
    
    def __init__(self, parent, title: str, group: Group = None):
        self.group: Group = None
        
        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.geometry("450x350")
        dialog.transient(parent)
        dialog.grab_set()
        
        # Form
        form = ttk.Frame(dialog, padding=20)
        form.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(form, text="Имя группы:").grid(row=0, column=0, sticky=tk.W, pady=5)
        name_entry = ttk.Entry(form, width=30)
        name_entry.grid(row=0, column=1, sticky=tk.W, pady=5)
        
        ttk.Label(form, text="API ключи:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        keys_frame = ttk.Frame(form)
        keys_frame.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        keys_text = tk.Text(keys_frame, height=5, width=30, bg='#2D2D3F', fg='#F8FAFC')
        keys_text.pack(side=tk.LEFT)
        
        keys_scroll = ttk.Scrollbar(keys_frame, orient=tk.VERTICAL, command=keys_text.yview)
        keys_text.config(yscrollcommand=keys_scroll.set)
        keys_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        ttk.Label(form, text="(по одному на строку)").grid(row=2, column=1, sticky=tk.W)
        
        ttk.Label(form, text="Разрешённые:").grid(row=3, column=0, sticky=tk.W, pady=5)
        allowed_entry = ttk.Entry(form, width=30)
        allowed_entry.grid(row=3, column=1, sticky=tk.W, pady=5)
        allowed_entry.insert(0, "*")
        
        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        def on_ok():
            name = name_entry.get().strip()
            keys_str = keys_text.get("1.0", tk.END).strip()
            allowed = allowed_entry.get().strip()
            
            if not name:
                messagebox.showerror("Ошибка", "Имя группы обязательно")
                return
            
            api_keys = [k.strip() for k in keys_str.split('\n') if k.strip()]
            
            self.group = Group(
                name=name,
                api_keys=api_keys,
                allowed_connections=allowed
            )
            dialog.destroy()
        
        ttk.Button(btn_frame, text="ОК", command=on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Fill if editing
        if group:
            name_entry.insert(0, group.name)
            keys_text.insert("1.0", '\n'.join(group.api_keys))
            allowed_entry.delete(0, tk.END)
            allowed_entry.insert(0, group.allowed_connections)
        
        dialog.wait_window()


def main():
    """Главная функция."""
    root = tk.Tk()
    app = LLMGuiApp(root)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app._on_close()


if __name__ == "__main__":
    main()