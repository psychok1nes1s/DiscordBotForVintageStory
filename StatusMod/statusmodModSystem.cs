using Vintagestory.API.Common;
using Vintagestory.API.Server;
using System.Net;
using Newtonsoft.Json;
using Vintagestory.GameContent;
using System.Text;
using System.Linq;
using System;
using System.Threading;
using System.Net.Http;

namespace StatusMod
{
    public class StatusModSystem : ModSystem, IDisposable
    {
        private ICoreServerAPI api;
        private HttpListener listener;
        private const string Url = "http://localhost:8080/status/";
        private readonly object _lock = new object();
        private readonly CancellationTokenSource _cts = new CancellationTokenSource();
        private ILogger _logger;
        private bool _disposed = false;
        private long _gameTickListenerId;
        private long _stormCheckTickListenerId;
        
        // Время ожидания запроса в миллисекундах
        private const int RequestTimeoutMs = 100;
        
        // Статус шторма для отслеживания изменений
        private bool _lastStormStatus = false;
        private bool _stormWarningIssued = false;
        
        // Добавляем информацию о шторме
        private class StormForecast
        {
            public bool IsActive { get; set; }
            public string Message { get; set; }
            public bool IsWarning { get; set; }
        }

        private const string DiscordBotUrl = "http://localhost:8081/status/notification";

        public override void StartServerSide(ICoreServerAPI api)
        {
            this.api = api ?? throw new ArgumentNullException(nameof(api));
            this._logger = api.Logger;
            
            // Регистрируем обработчик события выгрузки сервера
            api.Event.ServerRunPhase(EnumServerRunPhase.Shutdown, () => Dispose());
            
            try
            {
                if (!IsPortAvailable(8080))
                {
                    _logger.Error("Порт 8080 уже используется!");
                    return;
                }

                _logger.Event("Запускаю HTTP сервер для статуса на адресе " + Url);
                StartHttpServer();
                
                // Запускаем проверку шторма каждые 5 секунд
                _stormCheckTickListenerId = api.Event.RegisterGameTickListener(CheckTemporalStorm, 5000);
            }
            catch (Exception ex)
            {
                _logger.Error($"Не удалось запустить HTTP сервер: {ex}");
            }
        }

        private void StartHttpServer()
        {
            try
            {
                listener = new HttpListener();
                listener.Prefixes.Add(Url);
                listener.Start();
                
                _logger.Event("HTTP сервер успешно запущен на " + Url);
                
                // Инициируем первый асинхронный запрос
                listener.BeginGetContext(OnRequestReceived, listener);
                
                // Также регистрируем тик только для проверки состояния
                _gameTickListenerId = (long)api.Event.RegisterGameTickListener(CheckServerStatus, 60000);
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при запуске HTTP-сервера: {ex}");
            }
        }

        private void HandleHttpRequests(float dt)
        {
            if (_disposed || !listener.IsListening) return;

            // Вместо запуска нового потока для каждого запроса, проверим наличие запросов асинхронно
            try {
                IAsyncResult result = listener.BeginGetContext(OnRequestReceived, listener);
            }
            catch (Exception ex) {
                _logger?.Error($"Ошибка при начале прослушивания запросов: {ex}");
            }
        }

        private void OnRequestReceived(IAsyncResult result)
        {
            if (_disposed) return;

            HttpListenerResponse response = null;
            try
            {
                var listener = (HttpListener)result.AsyncState;
                if (!listener.IsListening) return;

                HttpListenerContext context = listener.EndGetContext(result);
                response = context.Response;

                // Убираем лишнее логирование
                // _logger.Event($"Получен запрос от {context.Request.RemoteEndPoint}");

                // Снова начинаем прослушивать для следующего запроса
                listener.BeginGetContext(OnRequestReceived, listener);

                // Готовим данные ответа
                var serverData = new
                {
                    playerCount = api.World.AllOnlinePlayers?.Length ?? 0,
                    players = api.World.AllOnlinePlayers?.Select(p => p.PlayerName).ToArray() ?? new string[0],
                    time = api.World.Calendar.PrettyDate(),
                    temporalStorm = GetTemporalStormStatus() ? "Активен" : "Неактивен"
                };

                string jsonResponse = JsonConvert.SerializeObject(serverData);
                byte[] buffer = Encoding.UTF8.GetBytes(jsonResponse);

                response.ContentType = "application/json";
                response.ContentLength64 = buffer.Length;
                response.AddHeader("Access-Control-Allow-Origin", "*");
                response.AddHeader("Cache-Control", "no-cache, no-store, must-revalidate");
                
                // Запись ответа максимально быстро
                try {
                    response.OutputStream.Write(buffer, 0, buffer.Length);
                    // Убираем лишнее логирование
                    // _logger.Event($"Отправлен ответ: {jsonResponse}");
                }
                catch (Exception ex) {
                    _logger.Error($"Ошибка при отправке ответа: {ex}");
                }
                finally {
                    try { response?.Close(); } catch { }
                }
            }
            catch (HttpListenerException ex)
            {
                _logger.Error($"Ошибка HttpListener: {ex}");
            }
            catch (Exception ex)
            {
                _logger?.Error($"Ошибка при обработке запроса: {ex}");
            }
            finally
            {
                try { response?.Close(); } catch { }
            }
        }

        private bool GetTemporalStormStatus()
        {
            if (_disposed || api == null) return false;
            
            try {
                var systems = api.ModLoader.GetModSystem<SystemTemporalStability>();
                if (systems?.StormData != null)
                {
                    return systems.StormData.nowStormActive;
                }
            }
            catch {
                // Игнорируем ошибки при получении статуса шторма
            }
            return false;
        }

        public override void Dispose()
        {
            // Защита от повторного вызова
            if (_disposed) return;
            _disposed = true;
            
            try
            {
                if (_cts != null && !_cts.IsCancellationRequested)
                {
                    _cts.Cancel();
                }
                
                if (api != null)
                {
                    try
                    {
                        api.Event.UnregisterGameTickListener(_gameTickListenerId);
                        api.Event.UnregisterGameTickListener(_stormCheckTickListenerId);
                    }
                    catch (Exception ex)
                    {
                        _logger?.Error($"Ошибка при отмене регистрации обработчика игровых тиков: {ex}");
                    }
                }
                
                lock (_lock)
                {
                    if (listener != null)
                    {
                        try
                        {
                            if (listener.IsListening)
                            {
                                listener.Stop();
                            }
                            listener.Close();
                        }
                        catch (Exception ex)
                        {
                            _logger?.Error($"Ошибка при закрытии HTTP слушателя: {ex}");
                        }
                        finally
                        {
                            listener = null;
                        }
                    }
                }
                
                if (_cts != null)
                {
                    try
                    {
                        _cts.Dispose();
                    }
                    catch (Exception ex)
                    {
                        _logger?.Error($"Ошибка при освобождении ресурсов токена отмены: {ex}");
                    }
                }
            }
            catch (Exception ex)
            {
                _logger?.Error($"Ошибка в методе Dispose: {ex}");
            }
            finally
            {
                try 
                { 
                    // Вызываем базовую реализацию
                    base.Dispose(); 
                } 
                catch (Exception ex) 
                {
                    _logger?.Error($"Ошибка в базовом методе Dispose: {ex}");
                }
            }
        }

        private bool IsPortAvailable(int port)
        {
            try
            {
                using (var testListener = new HttpListener())
                {
                    testListener.Prefixes.Add($"http://localhost:{port}/");
                    try
                    {
                        testListener.Start();
                        return true;
                    }
                    catch (HttpListenerException)
                    {
                        return false;
                    }
                }
            }
            catch
            {
                return false;
            }
        }

        private void CheckServerStatus(float dt)
        {
            // Этот метод просто периодически проверяет, что сервер работает
            if (_disposed) return;
            
            if (listener == null || !listener.IsListening)
            {
                _logger.Warning("HTTP сервер не отвечает, пробуем перезапустить");
                try
                {
                    if (listener != null)
                    {
                        try { listener.Stop(); } catch { }
                        try { listener.Close(); } catch { }
                    }
                    
                    StartHttpServer();
                }
                catch (Exception ex)
                {
                    _logger.Error($"Ошибка при перезапуске HTTP сервера: {ex}");
                }
            }
        }
        
        private void CheckTemporalStorm(float dt)
        {
            if (_disposed) return;
            
            try
            {
                var currentStormStatus = GetTemporalStormStatus();
                var systems = api.ModLoader.GetModSystem<SystemTemporalStability>();
                
                if (systems?.StormData != null)
                {
                    var stormData = systems.StormData;
                    
                    // Если шторм не активен, но скоро начнется
                    if (!currentStormStatus && !_stormWarningIssued && stormData.nextStormTotalDays - api.World.Calendar.TotalDays < 0.25)
                    {
                        // Отправляем предупреждение за ~6 часов игрового времени до шторма
                        _stormWarningIssued = true;
                        
                        string message = $"⚠️ **ВНИМАНИЕ**: Скоро начнется темпоральный шторм! Приготовьтесь!";
                        SendDiscordNotification(new StormForecast { IsActive = false, Message = message, IsWarning = true });
                        
                        _logger.Event("Отправлено предупреждение о приближающемся темпоральном шторме");
                    }
                    
                    // Если шторм только что начался
                    if (currentStormStatus && !_lastStormStatus)
                    {
                        string message = $"🌩️ **ТЕМПОРАЛЬНЫЙ ШТОРМ НАЧАЛСЯ**! Укройтесь в безопасном месте!";
                        SendDiscordNotification(new StormForecast { IsActive = true, Message = message, IsWarning = false });
                        
                        _logger.Event("Отправлено уведомление о начале темпорального шторма");
                    }
                    
                    // Если шторм только что закончился
                    if (!currentStormStatus && _lastStormStatus)
                    {
                        _stormWarningIssued = false; // Сбрасываем флаг предупреждения
                        string message = $"✨ **Темпоральный шторм закончился**. Мир снова безопасен.";
                        SendDiscordNotification(new StormForecast { IsActive = false, Message = message, IsWarning = false });
                        
                        _logger.Event("Отправлено уведомление об окончании темпорального шторма");
                    }
                    
                    // Обновляем последний известный статус
                    _lastStormStatus = currentStormStatus;
                }
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при проверке статуса шторма: {ex}");
            }
        }
        
        private void SendDiscordNotification(StormForecast forecast)
        {
            try
            {
                var notificationData = new
                {
                    type = "notification",
                    stormActive = forecast.IsActive,
                    stormWarning = forecast.IsWarning,
                    message = forecast.Message,
                    time = api.World.Calendar.PrettyDate()
                };
                
                _logger.Event($"Отправка уведомления в Discord: {forecast.Message}");
                
                using (var httpClient = new HttpClient())
                {
                    httpClient.Timeout = TimeSpan.FromSeconds(5);
                    
                    var content = new StringContent(
                        JsonConvert.SerializeObject(notificationData),
                        Encoding.UTF8,
                        "application/json");
                        
                    // Отправляем на правильный URL бота (порт 8081)
                    httpClient.PostAsync(DiscordBotUrl, content).GetAwaiter().GetResult();
                }
            }
            catch (Exception ex)
            {
                _logger.Error($"Ошибка при отправке уведомления в Discord: {ex}");
            }
        }
    }
}
