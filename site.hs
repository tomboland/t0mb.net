{-# LANGUAGE OverloadedStrings #-}

import qualified Cinema as C
import Data.Aeson (Value)
import Control.Monad (forM, forM_, when)
import Data.List (isPrefixOf)
import qualified Data.Map.Strict as M
import qualified Data.Set as S
import Hakyll hiding (renderTags)
import Hakyll.Core.Dependencies (DependencyKind(..))
import Text.HTML.TagSoup (Tag(..), parseTags, renderTags)
import System.Directory (doesDirectoryExist, listDirectory, removeFile)
import System.Environment (getArgs)
import System.FilePath ((</>), replaceExtension, takeExtension)

main :: IO ()
main = do
  args <- getArgs
  if "clean" `elem` args then hakyll (pure ()) else hakyll $ do
    cinema <- preprocess C.loadCinema
    let pages = C.pageViews cinema
        published = C.latestReviews cinema
        reviewPattern = fromList $ map (fromFilePath . C.str "source") published
        reviewBySource = M.fromList [(C.str "source" r, r) | r <- published]
        reviewFor identifier = case M.lookup (toFilePath identifier) reviewBySource of
          Just review -> review
          Nothing -> error ("Missing review: " ++ show identifier)
        expected = S.fromList $ "films/about/index.html" : [C.routePath url | (url,_,_) <- pages] ++ map (C.routePath . C.reviewUrl cinema) published
    -- Remove obsolete routes when tags/reviews/films are deleted or unpublished.
    preprocess $ mapM_ (prune expected) ["films", "directors"]
    match "css/*" $ route idRoute >> compile compressCssCompiler
    match ("images/**" .||. "js/*" .||. imagePattern) $ route idRoute >> compile copyFileCompiler
    match "templates/**" $ compile templateBodyCompiler
    match "content/home.md" $ compile pandocCompiler

    -- Track source data even though routes and joins are computed at rule evaluation.
    match ("cinema/*.json" .||. "cinema/reviews/*.md") $ version "data" $ compile getResourceString
    dependency <- makePatternDependency KindContent $ ("cinema/*.json" .||. "cinema/reviews/*.md") .&&. hasVersion "data"
    rulesExtraDependencies [dependency] $ do
      forM_ pages $ \(url,tpl,view) -> create [fromFilePath $ C.routePath url] $ do
        route idRoute
        compile $ do
          pageView <- if tpl == "film" then embedReviews view else pure view
          makeItem "" >>= renderCinema tpl pageView
      match reviewPattern $ do
        route $ customRoute $ \identifier ->
          C.routePath $ C.reviewUrl cinema $ reviewFor identifier
        compile $ do
          identifier <- getUnderlying
          let review=reviewFor identifier
              view=C.set [("nav_writing",C.val "true")] $ C.reviewView cinema review
          pandocCompiler
            >>= saveSnapshot "review-body"
            >>= loadAndApplyTemplate "templates/cinema/review.html" (C.viewContext view <> siteFields)
            >>= saveSnapshot "content"
            >>= wrapCinema view
      create ["index.html"] $ do
        route idRoute
        compile $ do
          posts <- fmap (take 3) . recentFirst =<< loadAllSnapshots "posts/*/index.md" "content"
          intro <- loadBody "content/home.md"
          introTitle <- getMetadataField' "content/home.md" "title"
          let view=C.set [("intro",C.val intro),("introTitle",C.val introTitle),("title",C.val "Home")] $ C.homeView cinema
              context = listField "posts" postCtx (pure posts) <> boolField "hasPosts" (const $ not $ null posts) <> C.viewContext view <> siteFields
          makeItem "" >>= loadAndApplyTemplate "templates/home.html" context
            >>= loadAndApplyTemplate "templates/default.html" context >>= relativizeUrls
      create ["archive.html"] $ do
        route idRoute
        compile $ do
          posts <- recentFirst =<< loadAllSnapshots ("posts/*/index.md" .||. (reviewPattern .&&. hasNoVersion)) "content"
          let context=listField "posts" postCtx (pure posts) <> constField "title" "archive" <> siteCtx
          makeItem "" >>= loadAndApplyTemplate "templates/archive.html" context
            >>= loadAndApplyTemplate "templates/default.html" context >>= relativizeUrls
      create ["rss.xml"] $ do
        route idRoute
        compile $ do
          posts <- fmap (take 20) . recentFirst =<< loadAllSnapshots ("posts/*/index.md" .||. (reviewPattern .&&. hasNoVersion)) "content"
          let absolute url = if "/" `isPrefixOf` url && not ("//" `isPrefixOf` url) then "https://t0mb.net" ++ url else url
          renderRss feedConfig (postCtx <> bodyField "description") (map (fmap $ withUrls absolute) posts)
    match "content/films-about.md" $ do
      route $ constRoute "films/about/index.html"
      compile $ do
        title <- getMetadataField' "content/films-about.md" "title"
        pandocCompiler >>= renderCinema "about" (C.obj [("title",C.val title),("nav_films",C.val "true")])
    match "posts/*/index.md" $ do
      route $ customRoute $ replaceExtension' . toFilePath
      compile $ pandocCompiler >>= saveSnapshot "content"
        >>= loadAndApplyTemplate "templates/post.html" postCtx
        >>= loadAndApplyTemplate "templates/default.html" siteCtx >>= relativizeUrls
    match "software.md" $ do
      route $ setExtension "html"
      compile $ pandocCompiler >>= loadAndApplyTemplate "templates/default.html" siteCtx >>= relativizeUrls

-- Load only the rendered Markdown, without a standalone review's navigation.
embedReviews :: Value -> Compiler Value
embedReviews view = do
  embedded <- forM (C.ls "reviews" view) $ \review -> do
    body <- loadSnapshotBody (fromFilePath $ C.str "source" review) "review-body"
    let prefix = "review-" ++ C.str "id" review ++ "-body-"
        url = C.str "url" review
        resolve link
          | null link || "/" `isPrefixOf` link = link
          | "#" `isPrefixOf` link = "#" ++ prefix ++ drop 1 link
          | ':' `elem` takeWhile (/='/') link = link
          | otherwise = url ++ link
        namespace (TagOpen name attrs) = TagOpen name
          [(key, if key `elem` ["id", "for"] then prefix ++ value
                 else if key `elem` ["aria-describedby", "aria-labelledby"] then unwords (map (prefix ++) $ words value)
                 else value) | (key,value) <- attrs]
        namespace tag = tag
        html = withUrls resolve $ renderTags $ map namespace $ parseTags body
    pure $ C.set [("htmlBody",C.val html),("image",C.reviewImage review)] review
  pure $ C.set [("embeddedReviews",C.values embedded)] view

renderCinema :: String -> Value -> Item String -> Compiler (Item String)
renderCinema template view item =
  loadAndApplyTemplate (fromFilePath $ "templates/cinema/"++template++".html") context item
    >>= wrapCinema view
  where context=C.viewContext view <> siteFields

wrapCinema :: Value -> Item String -> Compiler (Item String)
wrapCinema view item =
  loadAndApplyTemplate "templates/film-section.html" context item
    >>= loadAndApplyTemplate "templates/default.html" context >>= relativizeUrls
  where context=C.viewContext view <> siteFields

prune :: S.Set FilePath -> FilePath -> IO ()
prune expected relative = do
  let path="_site" </> relative
  exists <- doesDirectoryExist path
  when exists $ do
    names <- listDirectory path
    forM_ names $ \name -> do
      let child=relative </> name
      directory <- doesDirectoryExist ("_site" </> child)
      if directory then prune expected child else
        when (takeExtension child==".html" && not (S.member child expected)) $ removeFile ("_site" </> child)

replaceExtension' :: FilePath -> FilePath
replaceExtension' p = replaceExtension p "html"
imagePattern :: Pattern
imagePattern = "posts/**.jpg" .||. "posts/**.jpeg" .||. "posts/**.png" .||. "posts/**.gif" .||. "posts/**.webp" .||. "posts/**.avif"
siteCtx :: Context String
siteCtx = siteFields <> defaultContext
siteFields :: Context String
siteFields = constField "siteTitle" "t0mb.net" <> constField "siteDescription" "Brain spill"

postCtx :: Context String
postCtx = dateField "date" "%Y-%m-%d" <> defaultContext
feedConfig :: FeedConfiguration
feedConfig = FeedConfiguration "t0mb.net" "Brain spill" "Tom Boland" "" "https://t0mb.net"
