using Vintagestory.API.Common;
using Vintagestory.API.Server;
using System.Net;
using Newtonsoft.Json;
using Vintagestory.GameContent;
using System.Text;
using System.Linq;
using System;
using System.Threading;

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

        public override void StartServerSide(ICoreServerAPI api)
        {
            this.api = api ?? throw new ArgumentNullException(nameof(api));
            this._logger = api.Logger;
            try
            {
                if (!IsPortAvailable(8080))
                {
                    _logger.Error("Port 8080 is already in use!");
                    return;
                }

                StartHttpServer();
            }
            catch (Exception ex)
            {
                _logger.Error($"Failed to start HTTP server: {ex}");
            }
        }

        private void StartHttpServer()
        {
            listener = new HttpListener();
            listener.Prefixes.Add(Url);
            listener.Start();
            
            api.Event.RegisterGameTickListener(HandleHttpRequests, 1000);
        }

        private void HandleHttpRequests(float dt)
        {
            if (!listener.IsListening) return;

            lock (_lock)
            {
                try
                {
                    HttpListenerContext context = listener.GetContext();
                    HttpListenerResponse response = context.Response;

                    var serverData = new
                    {
                        playerCount = api.World.AllOnlinePlayers.Length,
                        players = api.World.AllOnlinePlayers.Select(p => p.PlayerName).ToArray(),
                        time = api.World.Calendar.PrettyDate(),
                        temporalStorm = GetTemporalStormStatus() ? "Active" : "Inactive"
                    };

                    string jsonResponse = JsonConvert.SerializeObject(serverData);
                    byte[] buffer = Encoding.UTF8.GetBytes(jsonResponse);

                    response.ContentType = "application/json";
                    response.ContentLength64 = buffer.Length;
                    response.AddHeader("Access-Control-Allow-Origin", "*");
                    
                    response.OutputStream.Write(buffer, 0, buffer.Length);
                    response.Close();
                }
                catch (Exception ex)
                {
                    _logger.Error($"Error handling request: {ex}");
                }
            }
        }

        private bool GetTemporalStormStatus()
        {
            var systems = api.ModLoader.GetModSystem<SystemTemporalStability>();
            if (systems?.StormData != null)
            {
                return systems.StormData.nowStormActive;
            }
            return false;
        }

        public override void Dispose()
        {
            if (listener != null && listener.IsListening)
            {
                listener.Stop();
                listener.Close();
            }
            base.Dispose();
        }

        private bool IsPortAvailable(int port)
        {
            using (var listener = new HttpListener())
            {
                listener.Prefixes.Add($"http://localhost:{port}/");
                try
                {
                    listener.Start();
                    return true;
                }
                catch (HttpListenerException)
                {
                    return false;
                }
            }
        }
    }
}
